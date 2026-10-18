"""把学生习惯的数学写法规范化为 `sympy_worker` 的白名单语法。

纯函数，只依赖标准库：子进程在 `-I` 模式下也能直接按文件路径加载本模块。
输出只使用字母变量、数字、`+ - * / ^ ( ) . ,` 与白名单函数名
（`sqrt sin cos tan asin acos atan log ln exp abs pi`）。

处理顺序：全角/符号 → 上标 → 根号 → LaTeX 片段 → 隐式乘法与分母约定。

有意的约定：`/` 后面紧跟"数字+字母"或"多个字母"组成的乘积单项时，按课本习惯
把整个单项视为分母：`k/2a` → `k/(2*a)`、`1/ab` → `1/(a*b)`。只在紧接 `/`
的那一个单项内生效，遇到 `+ - * / )` 或空白就停止；`1/2*a` 中的 `/` 后是纯数字，
不触发该约定。这不是通用数学语法，而是本系统对中学写法的有意解释。

无法识别的字符原样保留，交给 worker 的白名单校验拒绝，并给出可读的错误信息。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 白名单函数与常量。常量只有 pi；其余视为函数（`sin(` 不拆开、不插乘号）。
_FUNCTION_NAMES: tuple[str, ...] = (
    "asin",
    "acos",
    "atan",
    "sqrt",
    "sin",
    "cos",
    "tan",
    "log",
    "ln",
    "exp",
    "abs",
    "pi",
)
_CONSTANT_NAMES = frozenset({"pi"})
# 按长度降序匹配，保证 asin 不会被识别成 a*sin。
_NAME_MATCH_ORDER = tuple(sorted(_FUNCTION_NAMES, key=len, reverse=True))

_SUPERSCRIPT_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUPERSCRIPT_TABLE = str.maketrans(_SUPERSCRIPT_CHARS, "0123456789")
_SUPERSCRIPT_RE = re.compile(f"(?<!\\^)[{_SUPERSCRIPT_CHARS}]+")


def _build_fullwidth_table() -> dict[int, str]:
    """全角标点、数字、字母与常见数学符号的半角映射。"""

    table: dict[int, str] = {
        ord("（"): "(",
        ord("）"): ")",
        ord("＋"): "+",
        ord("－"): "-",
        ord("＝"): "=",
        ord("，"): ",",
        ord("．"): ".",
        ord("　"): " ",
        ord("："): ":",
        ord("；"): ";",
        ord("／"): "/",
        ord("＊"): "*",
        ord("＾"): "^",
        ord("［"): "[",
        ord("］"): "]",
    }
    for start, offset, count in (
        ("０", ord("0"), 10),
        ("Ａ", ord("A"), 26),
        ("ａ", ord("a"), 26),
    ):
        for index in range(count):
            table[ord(start) + index] = chr(offset + index)
    return table


_FULLWIDTH_TABLE = _build_fullwidth_table()
_SYMBOL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("×", "*"),
    ("·", "*"),
    ("⋅", "*"),
    ("÷", "/"),
    ("−", "-"),  # U+2212
    ("–", "-"),  # en dash
    # 补一个空格，避免 πx、2π 这类写法被当成多字母变量拆错（空白最后由分词器去掉）。
    ("π", "pi "),
    # 常见的 Unicode 分数字符，学生用输入法可能直接打出来。
    ("½", "(1/2)"),
    ("⅓", "(1/3)"),
    ("⅔", "(2/3)"),
    ("¼", "(1/4)"),
    ("¾", "(3/4)"),
    ("⅕", "(1/5)"),
    ("⅙", "(1/6)"),
    ("⅛", "(1/8)"),
)


def _to_halfwidth(text: str) -> str:
    text = text.translate(_FULLWIDTH_TABLE).replace("$", "")
    for raw, replacement in _SYMBOL_REPLACEMENTS:
        text = text.replace(raw, replacement)
    return text


def _convert_superscripts(text: str) -> str:
    """`x¹²` → `x^12`；连续上标数字合并。"""

    return _SUPERSCRIPT_RE.sub(
        lambda match: "^" + match.group(0).translate(_SUPERSCRIPT_TABLE), text
    )


def _convert_roots(text: str) -> str:
    """`√(` → `sqrt(`；`√x`、`√2`、`√ab` → `sqrt(原子)`。"""

    pieces: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "√":
            pieces.append(char)
            index += 1
            continue

        start = index + 1
        if start < length and text[start] == "(":
            # 已有括号组，直接把根号换成函数名即可。
            pieces.append("sqrt")
            index = start
            continue

        end = start
        if start < length and text[start].isdigit():
            while end < length and (text[end].isdigit() or text[end] == "."):
                end += 1
        elif (
            start < length
            and text[start].isascii()
            and text[start].isalpha()
        ):
            while (
                end < length
                and text[end].isascii()
                and text[end].isalpha()
            ):
                end += 1

        if end > start:
            pieces.append(f"sqrt({text[start:end]})")
            index = end
        else:
            # 后面没有可识别的原子，原样保留，交给白名单拒绝。
            pieces.append(char)
            index += 1
    return "".join(pieces)


def _take_braced(text: str, index: int) -> tuple[str, int] | None:
    """读取从 `index` 开始的 `{...}` 组（支持嵌套），返回内容与结束位置。"""

    if index >= len(text) or text[index] != "{":
        return None
    depth = 0
    for position in range(index, len(text)):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[index + 1 : position], position + 1
    return None


def _skip_spaces(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _convert_latex(text: str) -> str:
    """把常见的 LaTeX 片段转换成白名单语法；未知命令原样保留。"""

    pieces: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length and text[index + 1].isalpha():
            name_start = index + 1
            name_end = name_start
            while name_end < length and text[name_end].isalpha():
                name_end += 1
            name = text[name_start:name_end]
            cursor = _skip_spaces(text, name_end)

            if name == "frac":
                numerator = _take_braced(text, cursor)
                if numerator is not None:
                    numerator_text, after_numerator = numerator
                    denominator = _take_braced(
                        text, _skip_spaces(text, after_numerator)
                    )
                    if denominator is not None:
                        denominator_text, after_denominator = denominator
                        pieces.append(
                            "(("
                            + _convert_latex(numerator_text)
                            + ")/("
                            + _convert_latex(denominator_text)
                            + "))"
                        )
                        index = after_denominator
                        continue

            if name == "sqrt":
                root_index: str | None = None
                if cursor < length and text[cursor] == "[":
                    close = text.find("]", cursor + 1)
                    if close != -1:
                        root_index = text[cursor + 1 : close]
                        cursor = _skip_spaces(text, close + 1)
                radicand = _take_braced(text, cursor)
                if radicand is not None:
                    radicand_text, after_radicand = radicand
                    if root_index is None:
                        pieces.append(
                            "sqrt(" + _convert_latex(radicand_text) + ")"
                        )
                    else:
                        pieces.append(
                            "("
                            + _convert_latex(radicand_text)
                            + ")^(1/("
                            + _convert_latex(root_index)
                            + "))"
                        )
                    index = after_radicand
                    continue

            if name in ("cdot", "times"):
                pieces.append("*")
            elif name == "div":
                pieces.append("/")
            elif name == "pi":
                pieces.append("pi")
            elif name in ("left", "right"):
                pass
            elif name in _FUNCTION_NAMES:
                pieces.append(name)
            else:
                # 不认识的命令原样保留，让白名单给出可读的错误。
                pieces.append("\\" + name)
            index = name_end
            continue

        if char == "{":
            pieces.append("(")
        elif char == "}":
            pieces.append(")")
        else:
            pieces.append(char)
        index += 1
    return "".join(pieces)


@dataclass(frozen=True)
class _Token:
    """规范化过程中的词法单元；`implicit=True` 表示由隐式乘法补上的 `*`。"""

    kind: str  # num / name / op / paren / space / unknown
    text: str
    implicit: bool = False
    is_function: bool = False


def _match_name(text: str, index: int) -> str | None:
    """在 `index` 处匹配白名单函数/常量；后面紧跟字母时不算匹配。"""

    for name in _NAME_MATCH_ORDER:
        if not text.startswith(name, index):
            continue
        end = index + len(name)
        if end < len(text) and text[end].isascii() and text[end].isalpha():
            continue
        return name
    return None


def _needs_implicit(previous: _Token, current: _Token) -> bool:
    """两个相邻词法单元之间是否需要补乘号。"""

    if previous.kind == "unknown" or current.kind == "unknown":
        return False
    if (
        current.kind == "paren"
        and current.text == "("
        and previous.kind == "name"
        and previous.is_function
    ):
        # 函数调用：sin( 不插乘号。
        return False

    left = previous.kind in ("num", "name") or (
        previous.kind == "paren" and previous.text == ")"
    )
    right = current.kind in ("num", "name") or (
        current.kind == "paren" and current.text == "("
    )
    return left and right


def _append_token(tokens: list[_Token], token: _Token) -> None:
    if token.kind == "space":
        if tokens and tokens[-1].kind != "space":
            tokens.append(token)
        return

    previous = next(
        (item for item in reversed(tokens) if item.kind != "space"), None
    )
    if previous is not None and _needs_implicit(previous, token):
        tokens.append(_Token("op", "*", implicit=True))
    tokens.append(token)


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            _append_token(tokens, _Token("space", " "))
            index += 1
            continue

        if char.isdigit() or (
            char == "."
            and index + 1 < length
            and text[index + 1].isdigit()
        ):
            end = index
            seen_dot = False
            while end < length and (
                text[end].isdigit() or (text[end] == "." and not seen_dot)
            ):
                if text[end] == ".":
                    seen_dot = True
                end += 1
            _append_token(tokens, _Token("num", text[index:end]))
            index = end
            continue

        if char.isascii() and char.isalpha():
            name = _match_name(text, index)
            if name is not None:
                _append_token(
                    tokens,
                    _Token(
                        "name",
                        name,
                        is_function=name not in _CONSTANT_NAMES,
                    ),
                )
                index += len(name)
                continue

            # 连续字母（不是函数名）拆成单字母；紧跟的数字视为下标。
            end = index + 1
            while end < length and text[end].isdigit():
                end += 1
            _append_token(tokens, _Token("name", text[index:end]))
            index = end
            continue

        if char in "()":
            _append_token(tokens, _Token("paren", char))
        elif char in "+-*/^,":
            _append_token(tokens, _Token("op", char))
        else:
            _append_token(tokens, _Token("unknown", char))
        index += 1
    return tokens


def _matching_paren(tokens: list[_Token], index: int) -> int | None:
    depth = 0
    for position in range(index, len(tokens)):
        token = tokens[position]
        if token.kind == "paren" and token.text == "(":
            depth += 1
        elif token.kind == "paren" and token.text == ")":
            depth -= 1
            if depth == 0:
                return position
    return None


def _scan_denominator(
    tokens: list[_Token], start: int
) -> tuple[int | None, int, bool]:
    """扫描 `/` 后的乘积单项，返回（结束位置、因子数、是否含字母）。"""

    index = start
    end: int | None = None
    factors = 0
    has_letter = False
    length = len(tokens)
    while index < length:
        token = tokens[index]
        if token.kind == "space":
            break
        if token.kind == "num":
            factors += 1
            end = index + 1
            index += 1
            continue
        if token.kind == "name":
            if (
                token.is_function
                and index + 1 < length
                and tokens[index + 1].kind == "paren"
                and tokens[index + 1].text == "("
            ):
                close = _matching_paren(tokens, index + 1)
                if close is None:
                    break
                factors += 1
                has_letter = True
                end = close + 1
                index = close + 1
                continue
            factors += 1
            has_letter = True
            end = index + 1
            index += 1
            continue
        if token.kind == "op" and token.text == "^":
            index += 1
            continue
        if token.implicit and token.kind == "op" and token.text == "*":
            index += 1
            continue
        break
    return end, factors, has_letter


def _group_denominators(tokens: list[_Token]) -> list[_Token]:
    """按课本习惯把 `/` 后的乘积单项整体作为分母。"""

    result: list[_Token] = []
    index = 0
    length = len(tokens)
    while index < length:
        token = tokens[index]
        result.append(token)
        if token.kind == "op" and token.text == "/" and not token.implicit:
            end, factors, has_letter = _scan_denominator(tokens, index + 1)
            if end is not None and factors >= 2 and has_letter:
                result.append(_Token("paren", "("))
                result.extend(tokens[index + 1 : end])
                result.append(_Token("paren", ")"))
                index = end
                continue
        index += 1
    return result


def normalize(expr: str) -> str:
    """把学生写法转成 worker 的白名单语法。无法识别的字符原样保留。"""

    if not isinstance(expr, str):
        raise TypeError("表达式必须是字符串")
    text = _to_halfwidth(expr)
    text = _convert_superscripts(text)
    text = _convert_roots(text)
    text = _convert_latex(text)
    tokens = _group_denominators(_tokenize(text))
    return "".join(token.text for token in tokens if token.kind != "space").strip()

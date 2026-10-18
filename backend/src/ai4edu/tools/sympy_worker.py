"""SymPy 计算子进程。

从 stdin 读 JSON，逐个执行 `equal` / `solve` / `evaluate`，把结果写到 stdout。
每个表达式先用 `math_notation.normalize` 规范化学生写法，再做字符与标识符白名单
校验，最后用最小化 `global_dict` 的 `parse_expr` 解析，不使用 `eval`。
"""

from __future__ import annotations

import io
import json
import random
import re
import sys
import tokenize
from typing import Any

from sympy import (
    E,
    Abs,
    Float,
    Integer,
    Rational,
    Symbol,
    acos,
    asin,
    atan,
    cos,
    exp,
    log,
    oo,
    pi,
    simplify,
    sin,
    solve,
    sqrt,
    tan,
)
from sympy.parsing.sympy_parser import (
    convert_xor,
    parse_expr,
    standard_transformations,
)

try:
    from ai4edu.tools.math_notation import normalize
except ModuleNotFoundError:
    # `-I` 隔离模式且包不可导入时，按文件路径加载（math_notation 只用标准库）。
    import importlib.util
    from pathlib import Path

    _notation_path = Path(__file__).with_name("math_notation.py")
    _notation_spec = importlib.util.spec_from_file_location(
        "_ai4edu_math_notation", _notation_path
    )
    if _notation_spec is None or _notation_spec.loader is None:
        raise
    _notation_module = importlib.util.module_from_spec(_notation_spec)
    _notation_spec.loader.exec_module(_notation_module)
    normalize = _notation_module.normalize

_ALLOWED_CHARS_RE = re.compile(r"^[0-9a-zA-Z_+\-*/^()., ]+$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z]\d*$")
_MAX_EXPR_LENGTH = 300

_FUNCTIONS: dict[str, Any] = {
    "sqrt": sqrt,
    "pi": pi,
    "E": E,
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "asin": asin,
    "acos": acos,
    "atan": atan,
    "log": log,
    "ln": log,
    "exp": exp,
    "abs": Abs,
    "Rational": Rational,
    "oo": oo,
}
_ALLOWED_FUNCTION_NAMES = frozenset(_FUNCTIONS)
_TRANSFORMATIONS = standard_transformations + (convert_xor,)


class ExpressionError(ValueError):
    """表达式不符合白名单或无法解析。"""


def _identifiers(expression: str) -> list[str]:
    """用 Python 词法分析提取标识符，避免把数字里的 e 当成变量。"""

    names: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(expression).readline):
            if token.type == tokenize.NAME:
                names.append(token.string)
    except (tokenize.TokenError, IndentationError) as exc:
        raise ExpressionError(f"表达式无法解析：{exc}") from exc
    return names


def normalize_expression(expression: Any) -> str:
    """先把学生/模型的写法规范化，再做白名单校验。"""

    if not isinstance(expression, str):
        raise ExpressionError("表达式必须是字符串")
    return normalize(expression)


def validate_expression(expression: Any) -> str:
    if not isinstance(expression, str):
        raise ExpressionError("表达式必须是字符串")
    text = expression.strip()
    if not text:
        raise ExpressionError("表达式为空")
    if len(text) > _MAX_EXPR_LENGTH:
        raise ExpressionError(f"表达式长度不能超过 {_MAX_EXPR_LENGTH}")
    if not _ALLOWED_CHARS_RE.match(text):
        raise ExpressionError("表达式包含白名单之外的字符")
    if "__" in text:
        raise ExpressionError("表达式不能包含双下划线")

    for name in _identifiers(text):
        if name not in _ALLOWED_FUNCTION_NAMES and not _IDENTIFIER_RE.match(name):
            raise ExpressionError(f"不允许的标识符：{name}")
    return text


def _local_dict(expression: str) -> dict[str, Any]:
    local: dict[str, Any] = {}
    for name in _identifiers(expression):
        if name in _FUNCTIONS:
            local[name] = _FUNCTIONS[name]
        elif _IDENTIFIER_RE.match(name):
            local[name] = Symbol(name)
    return local


def parse_expression(expression: Any) -> Any:
    text = validate_expression(normalize_expression(expression))
    try:
        return parse_expr(
            text,
            local_dict=_local_dict(text),
            global_dict={
                "__builtins__": {},
                "Symbol": Symbol,
                "Integer": Integer,
                "Float": Float,
                "Rational": Rational,
            },
            transformations=_TRANSFORMATIONS,
        )
    except Exception as exc:  # sympy 抛出的异常类型很杂，统一转成业务错误
        raise ExpressionError(f"表达式无法解析：{exc}") from exc


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 1000 else text[:1000] + "…"


def _close(left: Any, right: Any) -> bool | None:
    """数值比较；无法比较时返回 None。"""

    symbols = sorted(left.free_symbols | right.free_symbols, key=lambda item: item.name)
    samples: list[dict[Any, Any]] = []
    if symbols:
        for _ in range(5):
            samples.append({symbol: random.uniform(1.2, 3.8) for symbol in symbols})
    else:
        samples.append({})

    compared = 0
    for substitution in samples:
        try:
            left_value = complex(left.evalf(subs=substitution))
            right_value = complex(right.evalf(subs=substitution))
        except Exception:
            continue
        if any(
            value != value or abs(value) == float("inf")
            for value in (left_value, right_value)
        ):
            continue
        compared += 1
        scale = 1.0 + max(abs(left_value), abs(right_value))
        if abs(left_value - right_value) > 1e-8 * scale:
            return False

    return True if compared else None


def _equal(operation: dict[str, Any]) -> dict[str, Any]:
    left = parse_expression(operation.get("left"))
    right = parse_expression(operation.get("right"))
    diff = simplify(left - right)
    if diff == 0:
        return {"ok": True, "result": "true", "error": None}

    try:
        decided = diff.equals(0)
    except Exception:
        decided = None
    if decided is True:
        return {"ok": True, "result": "true", "error": None}
    if decided is False:
        return {"ok": False, "result": "false", "error": None}

    numeric = _close(left, right)
    if numeric is True:
        return {"ok": True, "result": "true", "error": None}
    if numeric is False:
        return {"ok": False, "result": "false", "error": None}
    return {
        "ok": False,
        "result": _short(diff),
        "error": "无法判断两个表达式是否相等",
    }


def _solve(operation: dict[str, Any]) -> dict[str, Any]:
    equation = parse_expression(operation.get("equation"))
    symbol_name = operation.get("symbol")
    if not isinstance(symbol_name, str) or not _IDENTIFIER_RE.match(symbol_name):
        raise ExpressionError("symbol 必须是字母（可带数字下标）")
    symbol = Symbol(symbol_name)

    solutions = solve(equation, symbol)
    expect_raw = operation.get("expect")
    if expect_raw is None or expect_raw == "":
        return {"ok": True, "result": _short(solutions), "error": None}

    expect = parse_expression(expect_raw)
    found = False
    for solution in solutions:
        try:
            if simplify(solution - expect) == 0:
                found = True
                break
        except Exception:
            continue
    return {
        "ok": found,
        "result": _short(solutions),
        "error": None if found else "期望值不在解集中",
    }


def _evaluate(operation: dict[str, Any]) -> dict[str, Any]:
    expression = parse_expression(operation.get("expr"))
    raw_subs = operation.get("subs") or {}
    if not isinstance(raw_subs, dict):
        raise ExpressionError("subs 必须是对象")
    substitutions: dict[Any, Any] = {}
    for name, value in raw_subs.items():
        if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
            raise ExpressionError(f"subs 中的变量名不合法：{name!r}")
        substitutions[Symbol(name)] = parse_expression(value)

    result = expression.subs(substitutions)
    try:
        numeric = result.evalf()
    except Exception:
        numeric = result
    return {"ok": True, "result": _short(numeric), "error": None}


_EXPRESSION_FIELDS: dict[str, tuple[str, ...]] = {
    "equal": ("left", "right"),
    "solve": ("equation", "expect"),
    "evaluate": ("expr",),
}


def _normalized_fields(operation: dict[str, Any], kind: Any) -> dict[str, str]:
    """收集本操作中各表达式的规范化结果，供模型核对系统如何理解写法。"""

    normalized: dict[str, str] = {}
    for field in _EXPRESSION_FIELDS.get(kind if isinstance(kind, str) else "", ()):
        value = operation.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            normalized[field] = normalize(value)
        except Exception:
            continue
    return normalized


def _run_operation(operation: Any) -> dict[str, Any]:
    if not isinstance(operation, dict):
        return {
            "ok": False,
            "result": "",
            "error": "每个操作必须是对象",
            "normalized": {},
        }
    kind = operation.get("kind")
    normalized = _normalized_fields(operation, kind)
    try:
        if kind == "equal":
            result = _equal(operation)
        elif kind == "solve":
            result = _solve(operation)
        elif kind == "evaluate":
            result = _evaluate(operation)
        else:
            result = {
                "ok": False,
                "result": "",
                "error": f"未知操作类型：{kind!r}",
            }
    except ExpressionError as exc:
        return {
            "ok": False,
            "result": "",
            "error": str(exc),
            "normalized": normalized,
        }
    except Exception as exc:  # 计算过程异常不能带崩整个子进程
        return {
            "ok": False,
            "result": "",
            "error": f"计算失败：{exc}",
            "normalized": normalized,
        }
    result["normalized"] = normalized
    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": f"输入不是合法 JSON：{exc}", "results": []}))
        return

    operations = payload.get("operations") if isinstance(payload, dict) else None
    if not isinstance(operations, list):
        print(json.dumps({"error": "operations 必须是数组", "results": []}))
        return

    results = [_run_operation(operation) for operation in operations]
    print(json.dumps({"results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()

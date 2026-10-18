"""数学写法规范化：学生常见写法 → worker 白名单语法。"""

from __future__ import annotations

import pytest

from ai4edu.tools.math_notation import normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 隐式乘法
        ("4ac", "4*a*c"),
        ("2a", "2*a"),
        ("b^2-4ac", "b^2-4*a*c"),
        ("b²-4ac", "b^2-4*a*c"),
        ("2(a+b)", "2*(a+b)"),
        ("(a+b)(a-b)", "(a+b)*(a-b)"),
        ("a(b+c)", "a*(b+c)"),
        # 课本习惯：/ 后整个乘积单项作分母
        ("k/2a", "k/(2*a)"),
        ("1/ab", "1/(a*b)"),
        ("k/2a^2", "k/(2*a^2)"),
        ("1/2*a", "1/2*a"),
        # 根号与上标
        ("√(b^2-4ac)", "sqrt(b^2-4*a*c)"),
        ("√2", "sqrt(2)"),
        ("2√3", "2*sqrt(3)"),
        ("x¹²", "x^12"),
        # LaTeX 片段
        (
            r"\frac{-b+\sqrt{b^2-4ac}}{2a}",
            "((-b+sqrt(b^2-4*a*c))/(2*a))",
        ),
        (r"\sqrt[3]{8}", "(8)^(1/(3))"),
        (r"\frac{\frac{1}{2}}{a}", "((((1)/(2)))/(a))"),
        (r"\left(a+b\right)\times c", "(a+b)*c"),
        (r"\pi r^2", "pi*r^2"),
        # 运算符与函数
        ("3×4÷2", "3*4/2"),
        ("sin(x)", "sin(x)"),
        ("sqrt(x)", "sqrt(x)"),
        # 字母后的数字下标保留
        ("a1+a2", "a1+a2"),
        # 全角
        ("（a+b）", "(a+b)"),
        ("２（ａ＋ｂ）", "2*(a+b)"),
        # 多余空白
        ("  4 ac  ", "4*a*c"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_unicode_fractions() -> None:
    assert normalize("½·a") == "(1/2)*a"


def test_normalize_keeps_unknown_characters_for_worker_rejection() -> None:
    assert normalize("a∠b") == "a∠b"

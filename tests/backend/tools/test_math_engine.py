"""`math_engine`：子进程白名单、学生写法规范化与超时。"""

from __future__ import annotations

import pytest

from ai4edu.tools.math_engine import run as run_math

# 显式标记：从仓库根目录收集测试时 backend/pyproject.toml 的 asyncio_mode 不生效。
pytestmark = pytest.mark.asyncio


async def test_equal_accepts_student_and_latex_notation() -> None:
    results = await run_math(
        [
            {
                "kind": "equal",
                "left": "(-b+√(b²-4ac))/2a",
                "right": r"\frac{-b+\sqrt{b^2-4ac}}{2a}",
            }
        ]
    )

    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["result"] == "true"
    assert results[0]["normalized"] == {
        "left": "(-b+sqrt(b^2-4*a*c))/(2*a)",
        "right": "((-b+sqrt(b^2-4*a*c))/(2*a))",
    }


async def test_unicode_fraction_in_area_formula() -> None:
    # 学生常写 ½·BE·BD；½·a·k/2a 按课本习惯是 a·k/(2a)·½ = k/4。
    results = await run_math(
        [{"kind": "equal", "left": "½·a·k/2a", "right": "k/4"}]
    )

    assert results[0]["ok"] is True


async def test_unsupported_character_returns_readable_error() -> None:
    results = await run_math(
        [{"kind": "equal", "left": "a∠b", "right": "a"}]
    )

    assert results[0]["ok"] is False
    assert results[0]["error"]


async def test_solve_accepts_student_notation() -> None:
    results = await run_math(
        [{"kind": "solve", "equation": "k/4-5/4", "symbol": "k", "expect": "5"}]
    )

    assert results[0]["ok"] is True
    assert results[0]["error"] is None
    assert results[0]["normalized"]["equation"] == "k/4-5/4"


async def test_dunder_import_is_rejected() -> None:
    results = await run_math(
        [
            {"kind": "evaluate", "expr": "__import__('os')"},
            {"kind": "evaluate", "expr": "os.system"},
        ]
    )

    assert all(result["ok"] is False for result in results)
    assert all(result["error"] for result in results)


async def test_timeout_kills_worker() -> None:
    results = await run_math(
        [{"kind": "evaluate", "expr": "(x+1)^100000", "subs": {"x": "2"}}],
        timeout=0.01,
    )

    assert results[0]["ok"] is False
    assert "超时" in results[0]["error"]

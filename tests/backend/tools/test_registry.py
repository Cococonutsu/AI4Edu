"""`ToolRegistry`：注册、重名报错、按阶段与回合内冲突的可用性筛选。"""

from __future__ import annotations

import pytest

from ai4edu.tools.base import BaseTool
from ai4edu.tools.registry import ToolRegistry, build_registry, to_tool_schemas
from ai4edu.tools.record_diagnosis import record_diagnosis
from ai4edu.tools.web.search import web_search
from ai4edu.tutoring.state import Phase


def _names(registry: ToolRegistry, phase: Phase | str, **kwargs) -> list[str]:
    return [tool.name for tool in registry.available_for(phase, **kwargs)]


def test_duplicate_registration_raises():
    with pytest.raises(ValueError, match="重复注册"):
        ToolRegistry(web_search, web_search)


def test_build_registry_contains_all_tools():
    registry = build_registry()

    assert sorted(tool.name for tool in registry._tools.values()) == [
        "analyze_problem",
        "draw_figure",
        "record_diagnosis",
        "web_fetch",
        "web_search",
    ]
    assert registry.get("web_search") is web_search
    assert registry.get("不存在") is None


def test_available_tools_by_phase():
    registry = build_registry()

    # idle 还没有题目，不能诊断。
    assert _names(registry, Phase.idle) == [
        "analyze_problem",
        "draw_figure",
        "web_search",
        "web_fetch",
    ]
    for phase in (Phase.tutoring, Phase.extension, Phase.completed):
        assert _names(registry, phase) == [
            "record_diagnosis",
            "analyze_problem",
            "draw_figure",
            "web_search",
            "web_fetch",
        ]


def test_unavailable_after_filters_within_the_turn():
    """本回合 analyze_problem 成功后，record_diagnosis 从列表里消失。"""

    registry = build_registry()

    names = _names(registry, Phase.tutoring, succeeded={"analyze_problem"})

    assert "record_diagnosis" not in names
    assert names == ["analyze_problem", "draw_figure", "web_search", "web_fetch"]
    # 其它工具的成功不影响（没有声明冲突）。
    assert "record_diagnosis" in _names(
        registry, Phase.tutoring, succeeded={"web_search", "draw_figure"}
    )


def test_registry_subset_supports_injection():
    """测试可注入子集：只注册 web_search 时其余名字被跳过。"""

    registry = ToolRegistry(web_search)

    assert _names(registry, Phase.tutoring) == ["web_search"]
    schemas = to_tool_schemas(registry.available_for(Phase.idle))
    assert [schema.name for schema in schemas] == ["web_search"]


def test_unavailable_after_declared_on_conflicting_tool():
    """冲突声明长在工具上（record_diagnosis 声明对 analyze_problem 的冲突）。"""

    assert record_diagnosis.unavailable_after == ("analyze_problem",)
    # 基类默认无冲突。
    assert web_search.unavailable_after == ()
    assert isinstance(web_search, BaseTool)


def test_concurrency_safety_declarations():
    """并发安全声明（对齐 cc，当前循环串行，预留并行编排）：

    只读工具为 True；写辅导状态/数据库的 analyze_problem 与
    record_diagnosis 覆写为 False，并行执行时需独占。
    """
    from ai4edu.tools.analyze_problem import analyze_problem
    from ai4edu.tools.figure import draw_figure
    from ai4edu.tools.web.fetch import web_fetch

    assert web_search.is_concurrency_safe({}) is True
    assert web_fetch.is_concurrency_safe({}) is True
    assert draw_figure.is_concurrency_safe({}) is True
    assert analyze_problem.is_concurrency_safe({}) is False
    assert record_diagnosis.is_concurrency_safe({}) is False

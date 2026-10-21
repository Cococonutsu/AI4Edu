"""工具注册表：按会话阶段给出可用工具。"""

from __future__ import annotations

from collections.abc import Iterable

from ai4edu.api.base import ToolSchema
from ai4edu.tools.analyze_problem import analyze_problem
from ai4edu.tools.base import BaseTool
from ai4edu.tools.figure import draw_figure
from ai4edu.tools.record_diagnosis import record_diagnosis
from ai4edu.tools.web_fetch import web_fetch
from ai4edu.tools.web_search import web_search
from ai4edu.tutoring.state import Phase

_ALL_TOOLS: dict[str, BaseTool] = {
    tool.name: tool
    for tool in (
        analyze_problem,
        draw_figure,
        record_diagnosis,
        web_search,
        web_fetch,
    )
}

_PHASE_TOOL_NAMES: dict[Phase, tuple[str, ...]] = {
    # 点问题、核对与闲聊不需要工具：模型直接写正文就是回复。
    Phase.idle: ("analyze_problem", "draw_figure", "web_search", "web_fetch"),
    Phase.tutoring: (
        "record_diagnosis",
        "analyze_problem",
        "draw_figure",
        "web_search",
        "web_fetch",
    ),
    Phase.extension: (
        "record_diagnosis",
        "analyze_problem",
        "draw_figure",
        "web_search",
        "web_fetch",
    ),
    Phase.completed: (
        "record_diagnosis",
        "analyze_problem",
        "draw_figure",
        "web_search",
        "web_fetch",
    ),
}


def tools_for(phase: Phase | str) -> list[BaseTool]:
    phase = Phase(phase)
    return [_ALL_TOOLS[name] for name in _PHASE_TOOL_NAMES[phase]]


def get_tool(name: str) -> BaseTool | None:
    return _ALL_TOOLS.get(name)


def all_tools() -> list[BaseTool]:
    return list(_ALL_TOOLS.values())


def to_tool_schemas(tools: Iterable[BaseTool]) -> list[ToolSchema]:
    return [
        ToolSchema(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in tools
    ]

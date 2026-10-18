"""工具注册表：按会话阶段给出可用工具。"""

from __future__ import annotations

from collections.abc import Iterable

from ai4edu.tools.analyze_problem import analyze_problem
from ai4edu.tools.answer_directly import answer_directly
from ai4edu.tools.base import BaseTool
from ai4edu.tools.check_math import check_math
from ai4edu.tools.record_diagnosis import record_diagnosis
from ai4edu.tutoring.state import Phase

_ALL_TOOLS: dict[str, BaseTool] = {
    tool.name: tool
    for tool in (
        analyze_problem,
        answer_directly,
        check_math,
        record_diagnosis,
    )
}

_PHASE_TOOL_NAMES: dict[Phase, tuple[str, ...]] = {
    Phase.idle: ("analyze_problem", "answer_directly", "check_math"),
    Phase.tutoring: (
        "record_diagnosis",
        "answer_directly",
        "check_math",
        "analyze_problem",
    ),
    Phase.extension: (
        "record_diagnosis",
        "answer_directly",
        "check_math",
        "analyze_problem",
    ),
    Phase.completed: (
        "record_diagnosis",
        "answer_directly",
        "analyze_problem",
        "check_math",
    ),
}


def tools_for(phase: Phase | str) -> list[BaseTool]:
    phase = Phase(phase)
    return [_ALL_TOOLS[name] for name in _PHASE_TOOL_NAMES[phase]]


def get_tool(name: str) -> BaseTool | None:
    return _ALL_TOOLS.get(name)


def all_tools() -> list[BaseTool]:
    return list(_ALL_TOOLS.values())


def to_openai_tools(tools: Iterable[BaseTool]) -> list[dict]:
    return [tool.to_openai_tool() for tool in tools]

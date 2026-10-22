"""工具注册表（`docs/architecture.md` 第 5 节）。

对齐 cc 的做法：注册表是**运行时组装的对象**（`ToolRegistry`），由引擎统一
装配（`build_registry`），测试可注入子集；"哪些工具在当前条件下可用"
（会话阶段 + 本回合已成功的工具）全部收敛到这里。工具名只出现在本模块、
工具自身文件与提示词里；hooks 经工具自声明的 `establishes`/`unavailable_after`
推进回合状态，不写具体工具名。
"""

from __future__ import annotations

from collections.abc import Iterable

from ai4edu.models.contracts import ToolSchema
from ai4edu.tools.analyze_problem import analyze_problem
from ai4edu.tools.base import BaseTool
from ai4edu.tools.figure import draw_figure
from ai4edu.tools.record_diagnosis import record_diagnosis
from ai4edu.tools.web.fetch import web_fetch
from ai4edu.tools.web.search import web_search
from ai4edu.tutoring.state import Phase

# 按会话阶段的可用工具（idle 还没有题目，不能诊断；其余阶段全开）。
_PHASE_TOOL_NAMES: dict[Phase, tuple[str, ...]] = {
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


class ToolRegistry:
    """工具的注册、查找与按条件筛选（组装点见 `build_registry`）。"""

    def __init__(self, *tools: BaseTool) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """登记一个工具；同名重复注册直接报错。

        工具名是对模型的唯一标识，静默覆盖会让 tool_use 无法正确路由。
        """
        name = tool.name
        if name in self._tools:
            raise ValueError(f"工具重复注册：{name}")
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名字查找；查不到返回 None，由调用方转成给模型的错误结果。"""
        return self._tools.get(name)

    def available_for(
        self, phase: Phase | str, *, succeeded: Iterable[str] = ()
    ) -> list[BaseTool]:
        """当前条件下可用的工具：先按阶段取，再剔除与本回合已成功工具冲突的。

        冲突由工具自己声明（`BaseTool.unavailable_after`），如
        `record_diagnosis` 在 `analyze_problem` 成功后本回合不可用。
        """
        succeeded_names = set(succeeded)
        available: list[BaseTool] = []
        for name in _PHASE_TOOL_NAMES[Phase(phase)]:
            tool = self._tools.get(name)
            if tool is None:
                continue
            if any(blocker in succeeded_names for blocker in tool.unavailable_after):
                continue
            available.append(tool)
        return available


def build_registry() -> ToolRegistry:
    """默认工具集；引擎统一装配，测试可注入子集。"""
    return ToolRegistry(
        analyze_problem,
        draw_figure,
        record_diagnosis,
        web_search,
        web_fetch,
    )


def to_tool_schemas(tools: Iterable[BaseTool]) -> list[ToolSchema]:
    """把工具实例转成发给模型的工具定义。"""
    return [
        ToolSchema(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in tools
    ]

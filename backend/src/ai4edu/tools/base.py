"""工具基类与执行上下文。对应 `docs/architecture.md` 第 5 节（工具）。"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ai4edu.config import Settings
from ai4edu.models.contracts import Provider
from ai4edu.models.content import ToolResultContent
from ai4edu.prompts import Reminders
from ai4edu.session.store import TurnStore
from ai4edu.storage.models import User
from ai4edu.tools.web.client import WebTools
from ai4edu.tutoring.framework import TutoringConfig
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState


@dataclass
class ToolResult:
    """工具执行结果：`content` 给模型看，`status_label` 给学生看。

    `content` 是 `ToolResultContent`（当前为纯文本，预留富内容块，定义见
    `models/content.py`）；经 `ToolRunnerAdapter` 渲染成文本后进入循环。
    `display` 是**允许下发**给浏览器的结构化展示数据（目前只有 `draw_figure`
    的图），不是工具参数或结果：它由本工具自己生成并挑选，学生端据此渲染。
    """

    content: ToolResultContent
    is_error: bool = False
    status_label: str = ""
    display: dict[str, Any] | None = None


@dataclass
class ToolContext:
    """一次学生回合内所有工具共享的上下文。

    `web` 是联网工具（搜索与网页抓取）的实现；没有配置时为 `None`，
    web 工具据此返回“联网功能未开通”的错误结果。
    """

    store: TurnStore
    settings: Settings
    config: TutoringConfig
    reminders: Reminders
    provider: Provider
    user: User
    conversation_id: int
    turn_id: str
    student_text: str
    attachment_ids: list[int] = field(default_factory=list)
    user_message_id: int | None = None
    state: TutorState = field(default_factory=lambda: TutorState.idle())
    problem: ProblemModel | None = None

    last_assistant_message_id: int | None = None
    _db_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    web: WebTools | None = None

    async def log_llm_call(
        self,
        *,
        purpose: str,
        model: str,
        prompt_version: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        step: int | None = None,
        thinking: str | None = None,
        error: str | None = None,
    ) -> None:
        # 同一回合内可能有并发的模型调用共用一个数据库会话；写库需串行。
        async with self._db_lock:
            await self.store.log_llm_call(
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                step=step,
                thinking=thinking,
                error=error,
            )
            await self.store.commit()

    async def persist_state(self, state: TutorState) -> None:
        """工具修改状态后立即写库，下一步系统提示词就能看到新状态。"""

        self.state = state
        await self.store.update_state(state.phase.value, state.to_json())
        await self.store.commit()


class BaseTool(ABC):
    """所有工具的基类。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    running_label: str = "处理中…"
    # 本回合内，这些工具成功执行一次后本工具即不可用（可用性由
    # `registry.available_for` 统一执行）。冲突声明写在受影响的工具上，
    # 如 record_diagnosis 声明 unavailable_after=("analyze_problem",)。
    unavailable_after: tuple[str, ...] = ()

    @abstractmethod
    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """执行工具。参数不合法时返回 `is_error=True`，不要抛异常。"""

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        """是否可与其他工具并行执行（对齐 cc 的同名声明）。

        当前循环串行执行，这是给将来并行编排预留的声明：只读工具保持
        默认 True；会修改辅导状态或数据库的工具覆写为 False，并行执行时
        需独占。
        """
        return True

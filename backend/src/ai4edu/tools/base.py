"""工具基类与执行上下文。"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ai4edu.api.base import Provider
from ai4edu.config import Settings
from ai4edu.prompts import Reminders
from ai4edu.session.store import TurnStore
from ai4edu.storage.models import User
from ai4edu.tutoring.framework import TutoringConfig
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState


@dataclass
class ToolResult:
    """工具执行结果：`content` 给模型看，`status_label` 给学生看。

    `display` 是**允许下发**给浏览器的结构化展示数据（目前只有 `draw_figure`
    的图），不是工具参数或结果：它由本工具自己生成并挑选，学生端据此渲染。
    """

    content: str
    is_error: bool = False
    status_label: str = ""
    display: dict[str, Any] | None = None


@dataclass
class ToolContext:
    """一次学生回合内所有工具共享的上下文。"""

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

    @abstractmethod
    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """执行工具。参数不合法时返回 `is_error=True`，不要抛异常。"""

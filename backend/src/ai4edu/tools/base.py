"""工具基类与执行上下文。"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.config import Settings
from ai4edu.storage.models import User
from ai4edu.storage.repos import conversations, llm_calls
from ai4edu.tutoring.framework import TutoringConfig
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState


@dataclass
class ToolResult:
    """工具执行结果：`content` 给模型看，`status_label` 给学生看。"""

    content: str
    is_error: bool = False
    status_label: str = ""


@dataclass
class ToolContext:
    """一次学生回合内所有工具共享的上下文。"""

    db: AsyncSession
    settings: Settings
    config: TutoringConfig
    client: AsyncOpenAI
    user: User
    conversation_id: int
    turn_id: str
    student_text: str
    attachment_ids: list[int] = field(default_factory=list)
    user_message_id: int | None = None
    state: TutorState = field(default_factory=lambda: TutorState.idle())
    problem: ProblemModel | None = None

    # 工具确认发送、但还没有被模型正文替代的回复（见 answer_directly）。
    pending_reply: str | None = None
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
        error: str | None = None,
    ) -> None:
        # 题目分析与独立复核并行调用模型，二者共用一个数据库会话；写库需串行。
        async with self._db_lock:
            await self._log_llm_call_locked(
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                error=error,
            )

    async def _log_llm_call_locked(
        self,
        *,
        purpose: str,
        model: str,
        prompt_version: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        error: str | None,
    ) -> None:
        await llm_calls.add(
            self.db,
            conversation_id=self.conversation_id,
            purpose=purpose,
            model=model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error=error,
        )
        await self.db.commit()

    async def persist_state(self, state: TutorState) -> None:
        """工具修改状态后立即写库，下一步系统提示词就能看到新状态。"""

        self.state = state
        await conversations.update_state(
            self.db,
            self.conversation_id,
            self.user.id,
            state.phase.value,
            state.to_json(),
        )
        await self.db.commit()


class BaseTool(ABC):
    """所有工具的基类。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    running_label: str = "处理中…"

    @abstractmethod
    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """执行工具。参数不合法时返回 `is_error=True`，不要抛异常。"""

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

"""一次学生回合需要的全部持久化读写（`docs/architecture.md` 第 2 节）。

`TurnStore` 对上提供高层接口（历史消息、辅导状态、当前题目、附件、
模型调用日志、证据记录），对下调用 `storage/repos`。所有读取都按
`user_id` 过滤。本模块不理解 SQL 细节以外的业务规则。
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.models.messages import Message
from ai4edu.storage.models import DEFAULT_CONVERSATION_TITLE, Attachment, Conversation, Problem
from ai4edu.storage.repos import (
    attachments as attachments_repo,
)
from ai4edu.storage.repos import (
    conversations as conversations_repo,
)
from ai4edu.storage.repos import (
    evidence as evidence_repo,
)
from ai4edu.storage.repos import (
    llm_calls as llm_calls_repo,
)
from ai4edu.storage.repos import (
    messages as messages_repo,
)
from ai4edu.storage.repos import (
    problems as problems_repo,
)


class TurnStore:
    """绑定 (数据库会话, user_id, conversation_id) 的回合存储。"""

    def __init__(
        self, db: AsyncSession, *, user_id: int, conversation_id: int
    ) -> None:
        self._db = db
        self.user_id = user_id
        self.conversation_id = conversation_id
        # 同一回合内若出现并发调用，模型日志的写库在此串行（原 ToolContext 锁移入）。
        self._llm_log_lock = asyncio.Lock()

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()

    # ---- 会话 ----

    async def get_conversation(self) -> Conversation | None:
        return await conversations_repo.get(
            self._db, self.conversation_id, self.user_id
        )

    async def is_default_title(self) -> bool:
        """会话标题是否还是默认的"新对话"（首回合应替换）。"""
        conversation = await self.get_conversation()
        return (
            conversation is not None
            and conversation.title == DEFAULT_CONVERSATION_TITLE
        )

    async def update_title(self, title: str) -> None:
        await conversations_repo.update_title(
            self._db, self.conversation_id, self.user_id, title
        )

    async def update_state(self, phase: str, state_json: dict | None) -> None:
        await conversations_repo.update_state(
            self._db, self.conversation_id, self.user_id, phase, state_json
        )

    async def touch(self) -> None:
        await conversations_repo.touch(
            self._db, self.conversation_id, self.user_id
        )

    # ---- 消息 ----

    async def append_messages(
        self, messages: list[Message]
    ) -> list[Message]:
        """按顺序追加消息（自动分配连续递增的 `seq`）并写回 `db_id`。"""

        rows = await messages_repo.append_messages(
            self._db,
            self.conversation_id,
            [message.to_append_dict() for message in messages],
        )
        for message, row in zip(messages, rows, strict=True):
            message.db_id = row.id
        return messages

    async def load_history(self) -> list[Message]:
        from ai4edu.session.recovery import repair_history

        rows = await messages_repo.list_for_conversation(
            self._db, self.conversation_id, self.user_id
        )
        return repair_history([Message.from_row(row) for row in rows])

    # ---- 辅导状态与题目 ----

    async def load_problem(self, problem_id: int) -> Problem | None:
        return await problems_repo.get_for_user(
            self._db, problem_id, self.user_id
        )

    async def add_problem(
        self,
        *,
        model_json: dict,
        confidence: str,
        framework_version: str,
    ) -> Problem:
        return await problems_repo.add(
            self._db,
            conversation_id=self.conversation_id,
            model_json=model_json,
            confidence=confidence,
            framework_version=framework_version,
        )

    # ---- 附件 ----

    async def list_attachments_by_ids(
        self, attachment_ids: list[int]
    ) -> list[Attachment]:
        return list(
            await attachments_repo.list_by_ids(
                self._db, attachment_ids, self.user_id
            )
        )

    async def link_attachments(self, attachment_ids: list[int]) -> None:
        await attachments_repo.link_to_conversation(
            self._db, attachment_ids, self.conversation_id, self.user_id
        )

    async def list_attachments_for_conversation(self) -> list[Attachment]:
        return list(
            await attachments_repo.list_for_conversation(
                self._db, self.conversation_id, self.user_id
            )
        )

    # ---- 证据与模型调用日志 ----

    async def add_evidence(self, **kwargs) -> None:
        await evidence_repo.add(
            self._db, conversation_id=self.conversation_id, **kwargs
        )

    async def log_llm_call(
        self,
        *,
        purpose: str,
        model: str,
        prompt_version: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_tokens: int | None = None,
        latency_ms: int | None = None,
        step: int | None = None,
        thinking: str | None = None,
        error: str | None = None,
    ) -> None:
        async with self._llm_log_lock:
            await llm_calls_repo.add(
                self._db,
                conversation_id=self.conversation_id,
                purpose=purpose,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                latency_ms=latency_ms,
                step=step,
                thinking=thinking,
                error=error,
            )
            await self._db.commit()


__all__ = ["TurnStore"]

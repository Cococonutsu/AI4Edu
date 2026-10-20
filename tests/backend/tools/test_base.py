"""`ToolContext.log_llm_call` 的并发写库。"""

from __future__ import annotations

import asyncio

import pytest

import ai4edu.session.store as store_module
from ai4edu.session.store import TurnStore
from ai4edu.tools.base import ToolContext

pytestmark = pytest.mark.asyncio


class _ReentryDetectingDb:
    """在 add / commit 中让出事件循环，并检测是否同时有第二个写者。"""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.reentered = False

    async def _enter(self) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active > 1:
            self.reentered = True
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.active -= 1

    async def commit(self) -> None:
        await self._enter()


async def test_log_llm_call_serializes_concurrent_writes(monkeypatch):
    """回归：错误记录 #8 —— 并发的模型调用同时写日志（共用一个数据库会话）。"""

    db = _ReentryDetectingDb()
    store = TurnStore(db, user_id=1, conversation_id=1)

    async def fake_add(session, **kwargs):
        await session._enter()
        return object()

    monkeypatch.setattr(store_module.llm_calls_repo, "add", fake_add)
    ctx = ToolContext(
        store=store,
        settings=None,
        config=None,
        reminders=None,
        provider=None,
        user=None,
        conversation_id=1,
        turn_id="turn-1",
        student_text="",
    )

    await asyncio.gather(
        ctx.log_llm_call(purpose="analyzer", model="test-model"),
        ctx.log_llm_call(purpose="tutor", model="test-model"),
    )

    assert db.reentered is False

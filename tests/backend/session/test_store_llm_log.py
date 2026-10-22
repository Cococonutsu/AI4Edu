"""`TurnStore.log_llm_call` 的并发写库串行（锁属会话组件）。"""

from __future__ import annotations

import asyncio

import pytest

import ai4edu.session.store as store_module
from ai4edu.session.store import TurnStore


class _ReentryDetectingDb:
    """进入写库期间再次进入即报错，用于验证串行。"""

    def __init__(self) -> None:
        self.depth = 0

    async def __aenter__(self) -> "_ReentryDetectingDb":
        assert self.depth == 0, "并发写库未被串行化"
        self.depth += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self.depth -= 1

    async def commit(self) -> None:
        async with self:
            pass

    def add(self, item: object) -> None:
        return None

    async def flush(self) -> None:
        async with self:
            pass


@pytest.mark.asyncio
async def test_log_llm_call_serializes_concurrent_writes(monkeypatch):
    db = _ReentryDetectingDb()
    store = TurnStore(db, user_id=1, conversation_id=1)

    async def fake_add(session, **kwargs):
        await session.flush()
        return object()

    monkeypatch.setattr(store_module.llm_calls_repo, "add", fake_add)

    await asyncio.gather(
        store.log_llm_call(purpose="tutor", model="m", step=1),
        store.log_llm_call(purpose="tutor", model="m", step=2),
    )

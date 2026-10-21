"""切到别的对话后，原对话继续在后台生成；每个学生同时生成的对话数有上限。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from ai4edu.config import get_settings
from ai4edu.core.events import TextDelta, TurnFinished, TurnStarted
from ai4edu.server.routes import messages as messages_routes
from ai4edu.server.routes.messages import SendMessageRequest, create_message
from ai4edu.server.streaming import RunRegistry

pytestmark = pytest.mark.asyncio


class _SlowEngine:
    """先发一个事件，然后等放行，再结束回合。"""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def run_turn(self, **kwargs):
        yield TurnStarted(turn_id="turn-1")
        await self.release.wait()
        yield TextDelta(text="好的")
        yield TurnFinished(status="complete", message_id=None)
        self.finished.set()


@pytest.fixture
def registry(monkeypatch) -> RunRegistry:
    fresh = RunRegistry()
    monkeypatch.setattr(messages_routes, "runs", fresh)
    return fresh


async def _start(session_factory, user, conversation_id):
    async with session_factory() as session:
        return await create_message(
            conversation_id,
            SendMessageRequest(text="在吗"),
            user=user,
            session=session,
        )


async def test_disconnect_does_not_cancel_generation(
    seed, session_factory, registry, monkeypatch
):
    """回归 #25：学生切到别的对话，原对话的生成被取消。"""

    engine = _SlowEngine()
    monkeypatch.setattr(messages_routes, "get_engine", lambda: engine)
    user, conversation_id = await seed()

    response = await _start(session_factory, user, conversation_id)
    stream = response.body_iterator
    first = await asyncio.wait_for(stream.__anext__(), timeout=5)
    assert "turn_started" in first
    assert registry.is_running(conversation_id)

    # 浏览器断开：流被关闭。
    await stream.aclose()
    await asyncio.sleep(0)
    assert registry.is_running(conversation_id), "断开连接不应取消生成"

    engine.release.set()
    await asyncio.wait_for(engine.finished.wait(), timeout=5)
    for _ in range(10):
        if not registry.is_running(conversation_id):
            break
        await asyncio.sleep(0.01)
    assert not registry.is_running(conversation_id), "任务结束后应自动移出登记表"


async def test_stop_still_cancels(seed, session_factory, registry, monkeypatch):
    engine = _SlowEngine()
    monkeypatch.setattr(messages_routes, "get_engine", lambda: engine)
    user, conversation_id = await seed()

    response = await _start(session_factory, user, conversation_id)
    await asyncio.wait_for(response.body_iterator.__anext__(), timeout=5)

    assert registry.cancel(conversation_id) is True
    for _ in range(10):
        if not registry.is_running(conversation_id):
            break
        await asyncio.sleep(0.01)
    assert not registry.is_running(conversation_id)
    await response.body_iterator.aclose()


async def test_concurrent_runs_are_limited_per_user(
    seed, session_factory, registry, monkeypatch
):
    monkeypatch.setenv("MAX_CONCURRENT_RUNS_PER_USER", "2")
    get_settings.cache_clear()
    engine = _SlowEngine()
    monkeypatch.setattr(messages_routes, "get_engine", lambda: engine)

    user, first_id = await seed()
    conversation_ids = [first_id]
    for _ in range(2):
        async with session_factory() as session:
            from ai4edu.storage.models import Conversation

            conversation = Conversation(user_id=user.id, title="另一个", phase="idle")
            session.add(conversation)
            await session.commit()
            conversation_ids.append(conversation.id)

    responses = []
    for conversation_id in conversation_ids[:2]:
        responses.append(await _start(session_factory, user, conversation_id))
    assert registry.running_for_user(user.id) == set(conversation_ids[:2])

    with pytest.raises(HTTPException) as caught:
        await _start(session_factory, user, conversation_ids[2])
    assert caught.value.status_code == 429
    assert "2 个对话" in str(caught.value.detail)

    engine.release.set()
    for response in responses:
        async for _ in response.body_iterator:
            pass
    for _ in range(10):
        if not registry.running_for_user(user.id):
            break
        await asyncio.sleep(0.01)
    assert registry.running_for_user(user.id) == set()

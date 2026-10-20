"""发送消息接口：请求会话必须在流式回答开始前关闭。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai4edu.core.events import TextDelta, TurnFinished, TurnStarted
from ai4edu.auth import sessions
from ai4edu.server.app import create_app
from ai4edu.server.routes import messages as messages_routes
from ai4edu.storage.db import get_session
from ai4edu.storage.models import Base, Conversation, User

pytestmark = pytest.mark.asyncio


async def test_request_session_closed_before_streaming(tmp_path: Path, monkeypatch):
    """回归：错误记录 #14 —— 回答过程中新建对话报 database is locked。"""

    db_path = tmp_path / "server.sqlite3"
    # 故意使用回滚日志模式（不开启 WAL），把“请求会话一直开着”的影响放大：
    # 长读事务会直接阻塞另一个请求的写入。
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", connect_args={"timeout": 0.2}
    )
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    class TrackingSession(AsyncSession):
        close_called = False

        async def close(self) -> None:
            self.close_called = True
            await super().close()

    tracking_factory = async_sessionmaker(
        engine, class_=TrackingSession, expire_on_commit=False
    )
    request_sessions: list[TrackingSession] = []
    closed_before_response: list[bool] = []
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            user = User(
                username="student_server",
                password_hash="not-used",
                display_name="小明",
                grade_band="junior",
                grade=8,
                role="student",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            conversation = Conversation(
                user_id=user.id, title="测试", phase="idle"
            )
            session.add(conversation)
            await session.flush()
            token = await sessions.create(session, user.id)
            conversation_id = conversation.id
            await session.commit()

        started = asyncio.Event()
        release = asyncio.Event()

        class SlowEngine:
            async def run_turn(self, **kwargs):
                started.set()
                await release.wait()
                yield TurnStarted(turn_id="turn-1")
                yield TextDelta(text="好的")
                yield TurnFinished(status="complete", message_id=None)

        async def override_get_session():
            async with tracking_factory() as session:
                request_sessions.append(session)
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        def fake_get_engine():
            return SlowEngine()

        original_streaming_response = messages_routes.StreamingResponse

        def tracking_streaming_response(*args, **kwargs):
            # 构造流式响应时，请求会话必须已经关闭。
            closed_before_response.append(
                bool(request_sessions and request_sessions[-1].close_called)
            )
            return original_streaming_response(*args, **kwargs)

        app = create_app()
        app.dependency_overrides[get_session] = override_get_session
        monkeypatch.setattr(messages_routes, "get_engine", fake_get_engine)
        monkeypatch.setattr(
            messages_routes, "StreamingResponse", tracking_streaming_response
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={sessions.COOKIE_NAME: token},
        ) as client:
            first = asyncio.create_task(
                client.post(
                    f"/api/conversations/{conversation_id}/messages",
                    json={"text": "在吗"},
                )
            )
            await asyncio.wait_for(started.wait(), timeout=5)

            # 流式回答还没结束：另一个请求新建会话必须成功。
            second = await asyncio.wait_for(
                client.post("/api/conversations", json={}), timeout=5
            )
            assert second.status_code == 201
            assert closed_before_response == [True]

            release.set()
            first_response = await asyncio.wait_for(first, timeout=5)
            assert first_response.status_code == 200
    finally:
        await engine.dispose()

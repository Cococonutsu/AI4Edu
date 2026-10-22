"""跨学生数据隔离：一名学生无法访问另一名学生的会话与附件。

学生边界的可执行证明（根 AGENTS.md 硬性规则 5）：所有越权访问一律 404，
会话列表互不可见。
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth import sessions
from ai4edu.server.app import create_app
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User

pytestmark = pytest.mark.asyncio

# 最小 PNG 头 + 填充，足够通过魔数检测。
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _override_session(session_factory):
    async def _get_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _get_session


async def _new_token(session_factory, user_id: int) -> str:
    async with session_factory() as session:
        token = await sessions.create(session, user_id)
        await session.commit()
    return token


async def _second_student(session_factory) -> User:
    async def _action(session: AsyncSession) -> User:
        user = User(
            username="student_b_isolation",
            password_hash="not-used",
            display_name="学生乙",
            grade_band="junior",
            grade=8,
            role="student",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async with session_factory() as session:
        return await _action(session)


@pytest_asyncio.fixture
async def app(session_factory):
    application = create_app()
    application.dependency_overrides[get_session] = _override_session(session_factory)
    return application


@pytest_asyncio.fixture
async def student_a(app, session_factory, seed):
    """学生甲：已登录，带一个会话和一张附件。"""
    user, conversation_id = await seed()
    token = await _new_token(session_factory, user.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={sessions.COOKIE_NAME: token},
    ) as client:
        upload = await client.post(
            "/api/attachments",
            files={"file": ("a.png", _PNG_BYTES, "image/png")},
        )
        assert upload.status_code == 201
        yield client, user, conversation_id, upload.json()["id"]


@pytest_asyncio.fixture
async def student_b(app, session_factory):
    """学生乙：已登录，无任何数据。"""
    user = await _second_student(session_factory)
    token = await _new_token(session_factory, user.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={sessions.COOKIE_NAME: token},
    ) as client:
        yield client, user


async def test_student_b_cannot_see_student_a_conversations(student_a, student_b):
    _, user_a, conversation_id, _ = student_a
    client_b, user_b = student_b

    listing = await client_b.get("/api/conversations")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == []

    detail = await client_b.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 404
    assert user_a.id != user_b.id


async def test_student_b_cannot_modify_or_delete_student_a_conversation(
    student_a, student_b
):
    _, _, conversation_id, _ = student_a
    client_b, _ = student_b

    renamed = await client_b.patch(
        f"/api/conversations/{conversation_id}", json={"title": "偷改"}
    )
    assert renamed.status_code == 404

    deleted = await client_b.delete(f"/api/conversations/{conversation_id}")
    assert deleted.status_code == 404


async def test_student_b_cannot_message_or_stop_student_a_conversation(
    student_a, student_b
):
    _, _, conversation_id, _ = student_a
    client_b, _ = student_b

    sent = await client_b.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "hi"}
    )
    assert sent.status_code == 404

    stopped = await client_b.post(f"/api/conversations/{conversation_id}/stop")
    assert stopped.status_code == 404


async def test_student_b_cannot_download_student_a_attachment(student_a, student_b):
    _, _, _, attachment_id = student_a
    client_b, _ = student_b

    response = await client_b.get(f"/api/attachments/{attachment_id}")
    assert response.status_code == 404


async def test_student_b_cannot_attach_into_student_a_conversation(
    student_a, student_b
):
    _, _, conversation_id, _ = student_a
    client_b, _ = student_b

    response = await client_b.post(
        "/api/attachments",
        data={"conversation_id": str(conversation_id)},
        files={"file": ("b.png", _PNG_BYTES, "image/png")},
    )
    assert response.status_code == 404

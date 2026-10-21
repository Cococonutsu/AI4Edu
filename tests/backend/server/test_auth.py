"""`/api/auth/me`：查看与修改自己的名字、年级。"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio

from ai4edu.auth import sessions
from ai4edu.auth.passwords import hash_password
from ai4edu.server.app import create_app
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User

pytestmark = pytest.mark.asyncio


def _override_session(session_factory):
    """让路由与 `current_user` 共用测试数据库的会话。"""

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


@pytest_asyncio.fixture
async def app(session_factory):
    application = create_app()
    application.dependency_overrides[get_session] = _override_session(session_factory)
    return application


@pytest_asyncio.fixture
async def anonymous(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def authenticated(app, session_factory, seed):
    """已登录的学生客户端，返回 `(client, user)`。"""

    user, _ = await seed()
    token = await _new_token(session_factory, user.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={sessions.COOKIE_NAME: token},
    ) as client:
        yield client, user


async def test_update_name_and_grade(authenticated):
    client, user = authenticated

    response = await client.patch(
        "/api/auth/me",
        json={"display_name": "  小红  ", "grade": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["username"] == user.username
    assert body["display_name"] == "小红"
    assert body["grade"] == 10
    assert body["grade_band"] == "senior"
    assert body["role"] == "student"
    assert body["is_active"] is True


async def test_update_only_display_name(authenticated):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json={"display_name": "小红"})

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "小红"
    assert body["grade"] == 8
    assert body["grade_band"] == "junior"


async def test_update_only_grade(authenticated):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json={"grade": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "小明"
    assert body["grade"] == 3
    assert body["grade_band"] == "primary"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"display_name": "   "}, "名字不能为空"),
        ({"display_name": "字" * 33}, "名字不能超过 32 个字符"),
    ],
)
async def test_invalid_display_name(authenticated, payload, detail):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == detail
    # 校验失败时不改动已有资料。
    assert (await client.get("/api/auth/me")).json()["display_name"] == "小明"


@pytest.mark.parametrize("grade", [0, 13])
async def test_grade_out_of_range(authenticated, grade):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json={"grade": grade})

    assert response.status_code == 422
    assert response.json()["detail"] == "年级必须是 1–12 的整数"
    assert (await client.get("/api/auth/me")).json()["grade"] == 8


async def test_grade_must_be_integer(authenticated):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json={"grade": "九"})

    assert response.status_code == 422
    # 类型错误由 Pydantic 报出，detail 是错误列表；其中仍是中文说明。
    assert "年级必须是 1–12 的整数" in json.dumps(response.json(), ensure_ascii=False)
    assert (await client.get("/api/auth/me")).json()["grade"] == 8


async def test_requires_at_least_one_field(authenticated):
    client, _ = authenticated

    response = await client.patch("/api/auth/me", json={})

    assert response.status_code == 422
    assert response.json()["detail"] == "请至少提供名字或年级"


async def test_rejects_other_fields(authenticated):
    client, _ = authenticated

    response = await client.patch(
        "/api/auth/me", json={"display_name": "小红", "role": "admin"}
    )

    assert response.status_code == 422
    body = (await client.get("/api/auth/me")).json()
    assert body["display_name"] == "小明"
    assert body["role"] == "student"


async def test_requires_login(anonymous):
    response = await anonymous.patch("/api/auth/me", json={"display_name": "小红"})

    assert response.status_code == 401


async def test_new_name_visible_after_relogin(authenticated, session_factory, app):
    client, user = authenticated
    response = await client.patch("/api/auth/me", json={"display_name": "小红"})
    assert response.status_code == 200

    # 给该学生设置可登录的密码，再用登录接口拿一个新会话（相当于重新登录）。
    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        stored.password_hash = hash_password("secret123")
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as fresh:
        login = await fresh.post(
            "/api/auth/login",
            json={"username": user.username, "password": "secret123"},
        )
        assert login.status_code == 200
        me = await fresh.get("/api/auth/me")

    assert me.status_code == 200
    assert me.json()["display_name"] == "小红"

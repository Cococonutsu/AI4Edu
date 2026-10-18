"""登录会话：随机 token 只发给浏览器，数据库存 SHA-256。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai4edu.config import get_settings
from ai4edu.storage.models import AuthSession, utcnow

COOKIE_NAME = "ai4edu_session"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create(
    session: AsyncSession, user_id: int, ttl_hours: int | None = None
) -> str:
    """创建登录会话，返回原始 token（仅此一次可见）。"""
    if ttl_hours is None:
        ttl_hours = get_settings().session_ttl_hours
    token = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(auth_session)
    await session.flush()
    return token


async def validate(session: AsyncSession, token: str) -> AuthSession | None:
    """返回未过期的会话并预加载用户；无效或过期返回 None。"""
    if not token:
        return None
    result = await session.execute(
        select(AuthSession)
        .where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.expires_at > utcnow(),
        )
        .options(selectinload(AuthSession.user))
    )
    return result.scalar_one_or_none()


async def delete(session: AsyncSession, token: str) -> bool:
    """删除指定 token 的会话；返回是否实际删除。"""
    result = await session.execute(
        sql_delete(AuthSession).where(AuthSession.token_hash == hash_token(token))
    )
    return bool(result.rowcount)


async def delete_all_for_user(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        sql_delete(AuthSession).where(AuthSession.user_id == user_id)
    )
    return int(result.rowcount or 0)


async def delete_expired(session: AsyncSession) -> int:
    result = await session.execute(
        sql_delete(AuthSession).where(AuthSession.expires_at <= utcnow())
    )
    return int(result.rowcount or 0)

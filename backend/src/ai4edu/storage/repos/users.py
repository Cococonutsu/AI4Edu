"""用户数据访问。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import User


async def create(
    session: AsyncSession,
    *,
    username: str,
    password_hash: str,
    display_name: str,
    grade_band: str,
    grade: int,
    role: str = "student",
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        grade_band=grade_band,
        grade=grade,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


async def set_password(session: AsyncSession, username: str, password_hash: str) -> User | None:
    user = await get_by_username(session, username)
    if user is None:
        return None
    user.password_hash = password_hash
    await session.flush()
    return user


async def set_active(session: AsyncSession, username: str, is_active: bool) -> User | None:
    user = await get_by_username(session, username)
    if user is None:
        return None
    user.is_active = is_active
    await session.flush()
    return user

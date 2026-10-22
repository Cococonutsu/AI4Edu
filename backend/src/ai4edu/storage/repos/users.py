"""用户数据访问。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import User
from ai4edu.tutoring.framework import grade_band_for
from ai4edu.utils.errors import ConfigError


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


MAX_DISPLAY_NAME_LENGTH = 32


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    display_name: str | None = None,
    grade: int | None = None,
) -> User:
    """更新学生的显示名与/或年级；校验、学段推导、写库一站式。

    路由只翻译 HTTP 状态码，不持有业务规则。
    """
    if display_name is None and grade is None:
        raise ConfigError("请至少提供名字或年级")

    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            raise ConfigError("名字不能为空")
        if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
            raise ConfigError(f"名字不能超过 {MAX_DISPLAY_NAME_LENGTH} 个字符")

    if grade is not None and not 1 <= grade <= 12:
        raise ConfigError("年级必须是 1–12 的整数")

    if display_name is not None:
        user.display_name = display_name
    if grade is not None:
        user.grade = grade
        user.grade_band = grade_band_for(grade)

    await session.commit()
    return user


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

"""FastAPI 鉴权依赖。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth import sessions
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User

def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
    )


async def current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 cookie `ai4edu_session` 取当前用户；无效、过期或停用均返回 401。"""
    token = request.cookies.get(sessions.COOKIE_NAME)
    if not token:
        raise _unauthorized()
    auth_session = await sessions.validate(session, token)
    if auth_session is None or auth_session.user is None:
        raise _unauthorized()
    user = auth_session.user
    if not user.is_active:
        raise _unauthorized()
    return user

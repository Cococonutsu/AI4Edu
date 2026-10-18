"""`/api/auth/*`：登录、登出、当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth import sessions
from ai4edu.auth.deps import current_user
from ai4edu.auth.passwords import verify_password
from ai4edu.config import get_settings
from ai4edu.server.schemas import LoginRequest, UserOut
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import users

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = "用户名或密码错误"


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = await users.get_by_username(session, payload.username.strip())
    # 用户不存在、密码错误、账号停用都返回同一句话，避免暴露账号是否存在。
    if (
        user is None
        or not user.is_active
        or not verify_password(user.password_hash, payload.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        )

    settings = get_settings()
    token = await sessions.create(session, user.id, settings.session_ttl_hours)
    response.set_cookie(
        key=sessions.COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    token = request.cookies.get(sessions.COOKIE_NAME)
    if token:
        await sessions.delete(session, token)
    settings = get_settings()
    response.delete_cookie(
        key=sessions.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)

"""`/api/auth/*`：登录、登出、当前用户与修改自己的资料。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth import sessions
from ai4edu.auth.deps import current_user
from ai4edu.auth.passwords import verify_password
from ai4edu.config import get_settings
from ai4edu.server.schemas import LoginRequest, UpdateMeRequest, UserOut
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import users
from ai4edu.tutoring.framework import grade_band_for

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = "用户名或密码错误"
_MAX_DISPLAY_NAME_LENGTH = 32


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
    # 顺带清理过期会话：登录是低频操作，借此避免 auth_sessions 无限堆积。
    await sessions.delete_expired(session)
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


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UpdateMeRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    """修改当前用户的名字和/或年级；用户名、角色等其他字段不接受修改。"""

    if payload.display_name is None and payload.grade is None:
        raise HTTPException(
            status_code=422,
            detail="请至少提供名字或年级",
        )

    new_display_name: str | None = None
    if payload.display_name is not None:
        new_display_name = payload.display_name.strip()
        if not new_display_name:
            raise HTTPException(
                status_code=422,
                detail="名字不能为空",
            )
        if len(new_display_name) > _MAX_DISPLAY_NAME_LENGTH:
            raise HTTPException(
                status_code=422,
                detail="名字不能超过 32 个字符",
            )

    if payload.grade is not None and not 1 <= payload.grade <= 12:
        raise HTTPException(
            status_code=422,
            detail="年级必须是 1–12 的整数",
        )

    if new_display_name is not None:
        user.display_name = new_display_name
    if payload.grade is not None:
        user.grade = payload.grade
        user.grade_band = grade_band_for(payload.grade)

    await session.commit()
    return UserOut.model_validate(user)

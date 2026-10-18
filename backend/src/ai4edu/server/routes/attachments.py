"""`/api/attachments/*`：图片上传与鉴权下载。"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth.deps import current_user
from ai4edu.config import get_settings
from ai4edu.server.schemas import AttachmentOut
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import attachments, conversations

router = APIRouter(prefix="/attachments", tags=["attachments"])

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_UNSUPPORTED = "仅支持 PNG、JPEG、WebP 图片"


def detect_image_type(data: bytes) -> tuple[str, str] | None:
    """按文件头魔数判断图片类型，返回 (mime_type, 扩展名)。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: UploadFile = File(...),
    conversation_id: int | None = Form(default=None),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AttachmentOut:
    if conversation_id is not None:
        conversation = await conversations.get(session, conversation_id, user.id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
            )

    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    await file.close()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="图片不能超过 10MB",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空"
        )

    detected = detect_image_type(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_UNSUPPORTED
        )
    mime_type, extension = detected

    settings = get_settings()
    relative_path = Path(str(user.id)) / f"{uuid4().hex}{extension}"
    destination = settings.uploads_dir / relative_path
    await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_bytes, data)

    record = await attachments.create(
        session,
        user_id=user.id,
        conversation_id=conversation_id,
        file_path=relative_path.as_posix(),
        mime_type=mime_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return AttachmentOut(
        id=record.id,
        url=f"/api/attachments/{record.id}",
        mime_type=record.mime_type,
        size=record.size,
        created_at=record.created_at,
    )


@router.get("/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    record = await attachments.get(session, attachment_id, user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在"
        )

    root = get_settings().uploads_dir.resolve()
    path = (root / record.file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="附件文件不存在"
        )
    return FileResponse(
        path,
        media_type=record.mime_type,
        filename=path.name,
        content_disposition_type="inline",
    )

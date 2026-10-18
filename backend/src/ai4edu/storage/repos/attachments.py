"""附件元数据访问。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Attachment, Conversation


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    conversation_id: int | None,
    file_path: str,
    mime_type: str,
    size: int,
    sha256: str,
) -> Attachment:
    attachment = Attachment(
        user_id=user_id,
        conversation_id=conversation_id,
        file_path=file_path,
        mime_type=mime_type,
        size=size,
        sha256=sha256,
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def get(session: AsyncSession, attachment_id: int, user_id: int) -> Attachment | None:
    result = await session.execute(
        select(Attachment).where(
            Attachment.id == attachment_id, Attachment.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def list_for_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Sequence[Attachment]:
    result = await session.execute(
        select(Attachment)
        .join(Conversation, Attachment.conversation_id == Conversation.id)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Attachment.user_id == user_id,
        )
        .order_by(Attachment.id)
    )
    return result.scalars().all()


async def list_by_ids(
    session: AsyncSession, attachment_ids: Sequence[int], user_id: int
) -> Sequence[Attachment]:
    if not attachment_ids:
        return []
    result = await session.execute(
        select(Attachment).where(
            Attachment.id.in_(attachment_ids), Attachment.user_id == user_id
        )
    )
    return result.scalars().all()

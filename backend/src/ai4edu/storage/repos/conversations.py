"""会话数据访问。所有读取都按 `user_id` 过滤。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Conversation, utcnow


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    title: str = "新对话",
    phase: str = "idle",
    state_json: dict | None = None,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id, title=title, phase=phase, state_json=state_json
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def list_for_user(session: AsyncSession, user_id: int) -> Sequence[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return result.scalars().all()


async def get(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Conversation | None:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def update_title(
    session: AsyncSession, conversation_id: int, user_id: int, title: str
) -> Conversation | None:
    conversation = await get(session, conversation_id, user_id)
    if conversation is None:
        return None
    conversation.title = title
    conversation.updated_at = utcnow()
    await session.flush()
    return conversation


async def update_state(
    session: AsyncSession,
    conversation_id: int,
    user_id: int,
    phase: str,
    state_json: dict | None,
) -> Conversation | None:
    conversation = await get(session, conversation_id, user_id)
    if conversation is None:
        return None
    conversation.phase = phase
    conversation.state_json = state_json
    conversation.updated_at = utcnow()
    await session.flush()
    return conversation


async def touch(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Conversation | None:
    conversation = await get(session, conversation_id, user_id)
    if conversation is None:
        return None
    conversation.updated_at = utcnow()
    await session.flush()
    return conversation


async def delete(session: AsyncSession, conversation_id: int, user_id: int) -> bool:
    conversation = await get(session, conversation_id, user_id)
    if conversation is None:
        return False
    await session.delete(conversation)
    await session.flush()
    return True

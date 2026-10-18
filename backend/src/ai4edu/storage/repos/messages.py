"""消息数据访问。读取通过会话归属校验 `user_id`。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Conversation, Message


async def append_messages(
    session: AsyncSession,
    conversation_id: int,
    messages: list[dict],
) -> list[Message]:
    """按给定顺序追加消息，自动分配连续递增的 `seq`。

    每个元素至少包含 `role`，内容块放在 `content_json`（兼容 `content`）。
    """
    result = await session.execute(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation_id)
    )
    next_seq = (result.scalar_one_or_none() or 0) + 1

    rows: list[Message] = []
    for offset, item in enumerate(messages):
        role = item.get("role")
        if not role:
            raise ValueError("消息缺少 role")
        content = item.get("content_json", item.get("content", []))
        row = Message(
            conversation_id=conversation_id,
            seq=next_seq + offset,
            role=role,
            content_json=content,
            turn_id=item.get("turn_id"),
        )
        session.add(row)
        rows.append(row)

    await session.flush()
    return rows


async def list_for_conversation(
    session: AsyncSession,
    conversation_id: int,
    user_id: int,
    *,
    after_seq: int | None = None,
) -> Sequence[Message]:
    statement = (
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .order_by(Message.seq)
    )
    if after_seq is not None:
        statement = statement.where(Message.seq > after_seq)
    result = await session.execute(statement)
    return result.scalars().all()


async def get_for_user(
    session: AsyncSession, message_id: int, user_id: int
) -> Message | None:
    result = await session.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id == message_id, Conversation.user_id == user_id)
    )
    return result.scalar_one_or_none()

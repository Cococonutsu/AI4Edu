"""模型调用日志数据访问。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Conversation, LLMCall


async def add(
    session: AsyncSession,
    *,
    conversation_id: int | None,
    purpose: str,
    model: str,
    prompt_version: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> LLMCall:
    call = LLMCall(
        conversation_id=conversation_id,
        purpose=purpose,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(call)
    await session.flush()
    return call


async def list_for_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Sequence[LLMCall]:
    result = await session.execute(
        select(LLMCall)
        .join(Conversation, LLMCall.conversation_id == Conversation.id)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .order_by(LLMCall.id)
    )
    return result.scalars().all()

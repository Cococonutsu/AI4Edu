"""题目模型数据访问。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Conversation, Problem


async def add(
    session: AsyncSession,
    *,
    conversation_id: int,
    model_json: dict,
    confidence: str,
    framework_version: str,
) -> Problem:
    problem = Problem(
        conversation_id=conversation_id,
        model_json=model_json,
        confidence=confidence,
        framework_version=framework_version,
    )
    session.add(problem)
    await session.flush()
    return problem


async def get_for_user(
    session: AsyncSession, problem_id: int, user_id: int
) -> Problem | None:
    result = await session.execute(
        select(Problem)
        .join(Conversation, Problem.conversation_id == Conversation.id)
        .where(Problem.id == problem_id, Conversation.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_for_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Sequence[Problem]:
    result = await session.execute(
        select(Problem)
        .join(Conversation, Problem.conversation_id == Conversation.id)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .order_by(Problem.id)
    )
    return result.scalars().all()

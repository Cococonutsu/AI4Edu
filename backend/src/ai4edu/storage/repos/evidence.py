"""证据记录数据访问。只追加，不提供修改或删除。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.storage.models import Conversation, EvidenceRecord


async def add(
    session: AsyncSession,
    *,
    conversation_id: int,
    problem_id: int | None,
    subtask_id: str | None,
    message_id: int | None = None,
    evidence_json: list | dict | None = None,
    solo_level: str | None = None,
    math_status: str,
    support_level: str,
    gaps_json: list | dict | None = None,
    decision_json: dict | None = None,
) -> EvidenceRecord:
    record = EvidenceRecord(
        conversation_id=conversation_id,
        problem_id=problem_id,
        subtask_id=subtask_id,
        message_id=message_id,
        evidence_json=evidence_json if evidence_json is not None else [],
        solo_level=solo_level,
        math_status=math_status,
        support_level=support_level,
        gaps_json=gaps_json if gaps_json is not None else [],
        decision_json=decision_json if decision_json is not None else {},
    )
    session.add(record)
    await session.flush()
    return record


async def list_for_conversation(
    session: AsyncSession, conversation_id: int, user_id: int
) -> Sequence[EvidenceRecord]:
    result = await session.execute(
        select(EvidenceRecord)
        .join(Conversation, EvidenceRecord.conversation_id == Conversation.id)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .order_by(EvidenceRecord.id)
    )
    return result.scalars().all()


async def list_for_problem(
    session: AsyncSession, problem_id: int, user_id: int
) -> Sequence[EvidenceRecord]:
    result = await session.execute(
        select(EvidenceRecord)
        .join(Conversation, EvidenceRecord.conversation_id == Conversation.id)
        .where(EvidenceRecord.problem_id == problem_id, Conversation.user_id == user_id)
        .order_by(EvidenceRecord.id)
    )
    return result.scalars().all()

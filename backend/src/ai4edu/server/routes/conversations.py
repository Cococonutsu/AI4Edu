"""`/api/conversations/*`：会话增删改查。别人的会话一律 404。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth.deps import current_user
from ai4edu.server.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
)
from ai4edu.server.serializers import visible_messages
from ai4edu.server.streaming import runs
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import conversations, messages

router = APIRouter(prefix="/conversations", tags=["conversations"])

_NOT_FOUND = "会话不存在"


async def _get_owned(
    session: AsyncSession, conversation_id: int, user_id: int
):
    conversation = await conversations.get(session, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return conversation


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    rows = await conversations.list_for_user(session, user.id)
    running = runs.running_for_user(user.id)
    return [
        ConversationOut.model_validate(row).model_copy(update={"running": row.id in running})
        for row in rows
    ]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    title = (payload.title if payload and payload.title else None) or "新对话"
    conversation = await conversations.create(session, user_id=user.id, title=title)
    return ConversationOut.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conversation = await _get_owned(session, conversation_id, user.id)
    rows = await messages.list_for_conversation(session, conversation_id, user.id)
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        messages=visible_messages(rows),
    ).model_copy(update={"running": runs.is_running(conversation.id)})


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    conversation = await _get_owned(session, conversation_id, user.id)
    conversation = await conversations.update_title(
        session, conversation.id, user.id, payload.title
    )
    assert conversation is not None
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await _get_owned(session, conversation_id, user.id)
    await conversations.delete(session, conversation_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

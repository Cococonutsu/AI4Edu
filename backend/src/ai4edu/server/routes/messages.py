"""`/api/conversations/{id}/messages` 与 `/stop`。

发送消息时启动独立的后台任务（自己的数据库会话），事件经 `asyncio.Queue`
转成 NDJSON。同一会话同时只允许一个生成任务。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth.deps import current_user
from ai4edu.config import get_settings
from ai4edu.core.events import AgentError, AgentEvent, TurnFinished
from ai4edu.core.query_engine import QueryEngine
from ai4edu.prompts import load_reminders
from ai4edu.server.streaming import event_to_json, runs
from ai4edu.storage.db import get_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import attachments, conversations
from ai4edu.tutoring.framework import load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["messages"])

_MAX_TEXT_LENGTH = 4000
_MAX_ATTACHMENTS = 4
_RUNNING_CONFLICT = "上一条消息还在回答中"
_GENERIC_ERROR = "出了点问题，请稍后再试。"


class SendMessageRequest(BaseModel):
    text: str = Field(default="", max_length=_MAX_TEXT_LENGTH)
    attachment_ids: list[int] = Field(default_factory=list, max_length=_MAX_ATTACHMENTS)

    @model_validator(mode="after")
    def _not_both_empty(self) -> "SendMessageRequest":
        if not self.text.strip() and not self.attachment_ids:
            raise ValueError("文字和图片不能都为空")
        return self


@lru_cache(maxsize=1)
def get_engine() -> QueryEngine:
    settings = get_settings()
    config = load_config(settings.config_dir)
    reminders = load_reminders(settings.config_dir)
    return QueryEngine(settings=settings, config=config, reminders=reminders)


async def _validate_conversation(
    session: AsyncSession, conversation_id: int, user: User
) -> None:
    conversation = await conversations.get(session, conversation_id, user.id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
        )


async def _validate_attachments(
    session: AsyncSession,
    conversation_id: int,
    user: User,
    attachment_ids: list[int],
) -> None:
    if not attachment_ids:
        return
    rows = await attachments.list_by_ids(session, attachment_ids, user.id)
    if len(rows) != len(attachment_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图片不存在或不属于当前学生",
        )
    for row in rows:
        if row.conversation_id is not None and row.conversation_id != conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图片不属于当前会话",
            )


async def _produce_events(
    queue: "asyncio.Queue[AgentEvent | None]",
    engine: QueryEngine,
    *,
    user: User,
    conversation_id: int,
    text: str,
    attachment_ids: list[int],
) -> None:
    last: AgentEvent | None = None

    def put(event: AgentEvent) -> None:
        nonlocal last
        last = event
        queue.put_nowait(event)

    try:
        async for event in engine.run_turn(
            user=user,
            conversation_id=conversation_id,
            text=text,
            attachment_ids=attachment_ids,
        ):
            put(event)
    except asyncio.CancelledError:
        if not isinstance(last, TurnFinished):
            put(TurnFinished("stopped"))
        raise
    except Exception:
        logger.exception("生成任务失败：conversation_id=%s", conversation_id)
        if not isinstance(last, TurnFinished):
            put(AgentError(_GENERIC_ERROR))
            put(TurnFinished("error"))
    finally:
        queue.put_nowait(None)


@router.post("/{conversation_id}/messages")
async def create_message(
    conversation_id: int,
    payload: SendMessageRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await _validate_conversation(session, conversation_id, user)

    attachment_ids = list(dict.fromkeys(payload.attachment_ids))
    await _validate_attachments(session, conversation_id, user, attachment_ids)
    # 校验到此结束。流式回答可能持续数分钟，期间不能让请求的数据库会话
    # 一直占着读事务；引擎在后台任务里使用自己的会话。
    await session.close()

    if runs.is_running(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_RUNNING_CONFLICT
        )

    queue: "asyncio.Queue[AgentEvent | None]" = asyncio.Queue()
    engine = get_engine()
    task = asyncio.create_task(
        _produce_events(
            queue,
            engine,
            user=user,
            conversation_id=conversation_id,
            text=payload.text,
            attachment_ids=attachment_ids,
        )
    )
    if not runs.start(conversation_id, task):
        task.cancel()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_RUNNING_CONFLICT
        )

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                line = json.dumps(event_to_json(event), ensure_ascii=False)
                yield line + "\n"
        finally:
            runs.finish(conversation_id, task)
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{conversation_id}/stop")
async def stop_generation(
    conversation_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    await _validate_conversation(session, conversation_id, user)
    return {"stopped": runs.cancel(conversation_id)}

"""`TutorEngine`：一个学生回合的完整执行与持久化。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.agent.content import ImageBlock, TextBlock
from ai4edu.agent.events import (
    AgentError,
    AgentEvent,
    TextDelta,
    TurnFinished,
    TurnStarted,
)
from ai4edu.agent.hooks import DiagnosisGuard
from ai4edu.agent.loop import AgentLoopFailure, agent_loop
from ai4edu.agent.messages import AgentMessage
from ai4edu.config import Settings
from ai4edu.llm.client import make_client
from ai4edu.llm.format import ImageLoader
from ai4edu.storage.db import async_session
from ai4edu.storage.models import User
from ai4edu.storage.repos import attachments, conversations, messages, problems
from ai4edu.tools.base import ToolContext
from ai4edu.tutoring.framework import TutoringConfig
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState

logger = logging.getLogger(__name__)

_GENERIC_ERROR = "出了点问题，请稍后再试。"
_EMPTY_REPLY_ERROR = "这次没能读懂题目，可以换一张更清晰的照片，或者把题目打字发给我。"
_MAX_ATTACHMENTS = 4


class TutorEngineError(Exception):
    """请求不合法（会话或附件不属于当前学生等）。"""


def _build_image_loader(
    settings: Settings, attachment_rows: list[object]
) -> ImageLoader:
    root = settings.uploads_dir.resolve()
    entries: dict[int, tuple[str, str]] = {
        int(getattr(row, "id")): (
            str(getattr(row, "mime_type")),
            str(getattr(row, "file_path")),
        )
        for row in attachment_rows
    }
    cache: dict[int, tuple[str, bytes]] = {}

    def load(attachment_id: int) -> tuple[str, bytes]:
        if attachment_id in cache:
            return cache[attachment_id]
        entry = entries.get(attachment_id)
        if entry is None:
            raise FileNotFoundError(f"附件 {attachment_id} 不存在")
        mime_type, relative = entry
        path: Path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise FileNotFoundError(f"附件 {attachment_id} 路径不合法")
        data = path.read_bytes()
        cache[attachment_id] = (mime_type, data)
        return mime_type, data

    return load


class TutorEngine:
    """持有进程级配置与模型客户端，每次 `run_turn` 使用独立数据库会话。"""

    def __init__(
        self,
        *,
        settings: Settings,
        config: TutoringConfig,
        client: AsyncOpenAI | None = None,
        max_steps: int = 8,
    ) -> None:
        self._settings = settings
        self._config = config
        self._client = client or make_client(settings)
        self._max_steps = max_steps

    async def run_turn(
        self,
        *,
        user: User,
        conversation_id: int,
        text: str,
        attachment_ids: list[int],
    ) -> AsyncIterator[AgentEvent]:
        async with async_session() as db:
            async for event in self._run(
                db,
                user=user,
                conversation_id=conversation_id,
                text=text,
                attachment_ids=attachment_ids,
            ):
                yield event

    async def _run(
        self,
        db: AsyncSession,
        *,
        user: User,
        conversation_id: int,
        text: str,
        attachment_ids: list[int],
    ) -> AsyncIterator[AgentEvent]:
        conversation = await conversations.get(db, conversation_id, user.id)
        if conversation is None:
            raise TutorEngineError("会话不存在")

        ids = list(dict.fromkeys(attachment_ids))
        if len(ids) > _MAX_ATTACHMENTS:
            raise TutorEngineError(f"一次最多发送 {_MAX_ATTACHMENTS} 张图片")

        attachment_rows = list(
            await attachments.list_by_ids(db, ids, user.id)
        )
        if len(attachment_rows) != len(ids):
            raise TutorEngineError("图片不存在或不属于当前学生")
        for row in attachment_rows:
            if row.conversation_id is not None and row.conversation_id != conversation_id:
                raise TutorEngineError("图片不属于当前会话")

        turn_id = uuid4().hex
        content_blocks: list[object] = []
        if text.strip():
            content_blocks.append(TextBlock(text=text))
        for attachment_id in ids:
            content_blocks.append(ImageBlock(attachment_id=attachment_id))

        user_message = AgentMessage(
            role="user", content=content_blocks, turn_id=turn_id
        )
        rows = await messages.append_messages(
            db, conversation_id, [user_message.to_append_dict()]
        )
        await db.commit()
        user_message.db_id = rows[0].id

        if conversation.title == "新对话":
            title = text.strip()[:20] or "图片题目"
            await conversations.update_title(db, conversation_id, user.id, title)
            await db.commit()

        history = [
            AgentMessage.from_row(row)
            for row in await messages.list_for_conversation(
                db, conversation_id, user.id
            )
        ]

        state = (
            TutorState.from_json(conversation.state_json)
            if conversation.state_json
            else TutorState.idle()
        )

        problem: ProblemModel | None = None
        if state.problem_id is not None:
            problem_row = await problems.get_for_user(db, state.problem_id, user.id)
            if problem_row is not None:
                try:
                    problem = ProblemModel.model_validate(problem_row.model_json)
                except Exception:
                    logger.exception("题目模型无法解析：problem_id=%s", state.problem_id)

        all_attachments = list(
            await attachments.list_for_conversation(db, conversation_id, user.id)
        )
        known_ids = {int(row.id) for row in all_attachments}
        all_attachments.extend(
            row for row in attachment_rows if int(row.id) not in known_ids
        )
        image_loader = _build_image_loader(self._settings, all_attachments)

        ctx = ToolContext(
            db=db,
            settings=self._settings,
            config=self._config,
            client=self._client,
            user=user,
            conversation_id=conversation_id,
            turn_id=turn_id,
            student_text=text,
            attachment_ids=ids,
            user_message_id=rows[0].id,
            state=state,
            problem=problem,
        )
        guard = DiagnosisGuard(
            state.phase, self._config.policy.diagnosis_retry_limit
        )

        yield TurnStarted(turn_id=turn_id)

        visible_parts: list[str] = []
        try:
            async for event in agent_loop(
                client=self._client,
                model=self._settings.llm_model_tutor,
                history=history,
                ctx=ctx,
                guard=guard,
                image_loader=image_loader,
                max_steps=self._max_steps,
            ):
                if isinstance(event, TextDelta):
                    visible_parts.append(event.text)
                yield event
        except asyncio.CancelledError:
            await conversations.touch(db, conversation_id, user.id)
            await db.commit()
            yield TurnFinished("stopped")
            raise
        except AgentLoopFailure as exc:
            logger.warning("回合被守卫结束：%s", exc.message)
            await conversations.touch(db, conversation_id, user.id)
            await db.commit()
            yield AgentError(exc.message)
            yield TurnFinished("error")
            return
        except Exception:
            logger.exception("辅导回合执行失败")
            try:
                await db.rollback()
                await conversations.touch(db, conversation_id, user.id)
                await db.commit()
            except Exception:
                logger.exception("回滚后更新会话时间失败")
            yield AgentError(_GENERIC_ERROR)
            yield TurnFinished("error")
            return

        # answer_directly 已确认发送，但模型没有另写正文：由引擎落地这条回复。
        if ctx.pending_reply and not visible_parts:
            reply_message = AgentMessage(
                role="assistant",
                content=[TextBlock(text=ctx.pending_reply)],
                turn_id=turn_id,
            )
            reply_rows = await messages.append_messages(
                db, conversation_id, [reply_message.to_append_dict()]
            )
            await db.commit()
            ctx.last_assistant_message_id = reply_rows[0].id
            yield TextDelta(ctx.pending_reply)

        if not visible_parts and not ctx.pending_reply:
            # 模型这一回合没有给学生任何正文（例如工具连续失败后放弃）：
            # 不能让学生面对空白，给一句可操作的提示。
            yield AgentError(_EMPTY_REPLY_ERROR)
            await conversations.touch(db, conversation_id, user.id)
            await db.commit()
            yield TurnFinished("error")
            return

        await conversations.touch(db, conversation_id, user.id)
        await db.commit()
        yield TurnFinished(
            status="complete", message_id=ctx.last_assistant_message_id
        )


__all__ = ["TutorEngine", "TutorEngineError"]

"""`QueryEngine`：组装一次学生回合的全部依赖并驱动循环（架构图第 2 节）。

负责：校验归属、保存用户消息、标题、加载历史/状态/题目/附件 → 构造
`TurnStore`、`ToolContext`、`TutoringHooks`、`ToolRunnerAdapter` 与
`call_model`（每步重新生成系统提示词、规范化消息、记录 `llm_calls`）→
驱动 `query_loop`，处理取消/错误/空回复。`provider` 由构造
函数注入（默认按配置创建），测试注入假 Provider。

对应 `docs/architecture.md` 第 2、3 节（组装依赖与回合流程）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.api.client import llm_credentials, make_provider
from ai4edu.config import Settings
from ai4edu.core.events import (
    AgentError,
    AgentEvent,
    TextDelta,
    TurnFinished,
    TurnStarted,
)
from ai4edu.core.query_loop import (
    LoopFailure,
    StepRequest,
    ToolOutcome,
    query_loop,
)
from ai4edu.hooks.guard import TurnGuard
from ai4edu.hooks.tutoring_hooks import TutoringHooks
from ai4edu.models.contracts import (
    ImageLoader,
    ModelEvent,
    ModelRequest,
    ModelUsage,
    Provider,
    ToolSchema,
    Usage,
)
from ai4edu.models.content import ImageBlock, TextBlock, tool_result_text
from ai4edu.models.messages import Message, prepare_messages
from ai4edu.prompts import Reminders
from ai4edu.prompts.builder import TUTOR_SYSTEM_VERSION, build_system_prompt
from ai4edu.prompts.reminders import Reminders
from ai4edu.session.store import TurnStore
from ai4edu.storage.db import async_session
from ai4edu.storage.models import User
from ai4edu.tools.base import ToolContext
from ai4edu.tools.registry import ToolRegistry, build_registry, to_tool_schemas
from ai4edu.tools.web.client import WebTools, make_web_tools
from ai4edu.tutoring.framework import TutoringConfig
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

_MAX_ATTACHMENTS = 4
# 读题那一步要输出思考 + 完整题目模型（参考解法、关系、子任务），8192 会被截断。
TUTOR_MAX_TOKENS = 16384


class QueryEngineError(Exception):
    """请求不合法（会话或附件不属于当前学生等）。"""


def _build_image_loader(
    settings: Settings, attachment_rows: list[Any]
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


@dataclass(frozen=True)
class _FailureTexts:
    """`LoopFailure.reason` → 学生可见的错误提示。"""

    network_error: str
    provider_error: str
    max_steps: str

    @classmethod
    def from_reminders(cls, reminders: Reminders) -> "_FailureTexts":
        return cls(
            network_error=reminders.student_network_error,
            provider_error=reminders.student_generic_error,
            max_steps=reminders.student_max_steps,
        )

    def for_reason(self, reason: str, fallback: str | None) -> str:
        if reason == "guard" and fallback:
            return fallback
        return getattr(self, reason, self.provider_error)


class ToolRunnerAdapter:
    """把工具注册表与 `ToolContext` 适配成循环需要的 `ToolRunner`。

    未知工具、非法参数、执行异常都在这里转成给模型的错误结果。
    """

    def __init__(self, ctx: ToolContext, reminders: Reminders, registry: ToolRegistry) -> None:
        self._ctx = ctx
        self._reminders = reminders
        self._registry = registry

    def schemas(self) -> list[ToolSchema]:
        return to_tool_schemas(
            self._registry.available_for(self._ctx.state.phase)
        )

    def running_label(self, name: str) -> str:
        tool = self._registry.get(name)
        return tool.running_label if tool is not None else name

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        input_error: str | None,
    ) -> ToolOutcome:
        tool = self._registry.get(name)
        if tool is None:
            return ToolOutcome(
                content=self._reminders.text("unknown_tool", name=name),
                is_error=True,
                status_label="工具不可用",
            )
        if arguments is None:
            return ToolOutcome(
                content=self._reminders.text(
                    "bad_tool_arguments", error=input_error or "", name=name
                ),
                is_error=True,
                status_label="参数错误",
            )
        try:
            result = await tool.execute(arguments, self._ctx)
        except Exception:
            logger.exception("工具 %s 执行失败", name)
            return ToolOutcome(
                content=self._reminders.text(
                    "tool_execution_failed", name=name
                ),
                is_error=True,
                status_label="工具出错",
            )
        return ToolOutcome(
            content=tool_result_text(result.content),
            is_error=result.is_error,
            status_label=result.status_label,
            display=result.display,
        )


class QueryEngine:
    """持有进程级配置与 Provider，每次 `run_turn` 使用独立数据库会话。"""

    def __init__(
        self,
        *,
        settings: Settings,
        config: TutoringConfig,
        reminders: Reminders,
        provider: Provider | None = None,
        web: WebTools | None = None,
        registry: ToolRegistry | None = None,
        max_steps: int = 8,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self._settings = settings
        self._config = config
        self._reminders = reminders
        self._provider = provider or make_provider(settings)
        self._web = web if web is not None else make_web_tools(settings)
        self._registry = registry or build_registry()
        if not llm_credentials(settings)[1]:
            # 没有密钥时登录、会话都能用，只有发消息会失败；建引擎时就说清楚。
            logger.error(
                "未配置 LLM_API_KEY（LLM_PROVIDER=deepseek 时可改用 DEEPSEEK_API_KEY）："
                "发送消息将失败。请复制 backend/.env.example 为 backend/.env 并填写密钥。"
            )
        self._max_steps = max_steps
        # 测试可注入临时数据库的会话工厂；生产环境使用进程级工厂。
        self._session_factory = session_factory or async_session

    async def run_turn(
        self,
        *,
        user: User,
        conversation_id: int,
        text: str,
        attachment_ids: list[int],
    ) -> AsyncIterator[AgentEvent]:
        async with self._session_factory() as db:
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
        store = TurnStore(db, user_id=user.id, conversation_id=conversation_id)
        conversation = await store.get_conversation()
        if conversation is None:
            raise QueryEngineError("会话不存在")

        ids = list(dict.fromkeys(attachment_ids))
        if len(ids) > _MAX_ATTACHMENTS:
            raise QueryEngineError(f"一次最多发送 {_MAX_ATTACHMENTS} 张图片")

        attachment_rows = await store.list_attachments_by_ids(ids)
        if len(attachment_rows) != len(ids):
            raise QueryEngineError("图片不存在或不属于当前学生")
        for row in attachment_rows:
            if (
                row.conversation_id is not None
                and row.conversation_id != conversation_id
            ):
                raise QueryEngineError("图片不属于当前会话")

        turn_id = uuid4().hex
        content_blocks: list[Any] = []
        if text.strip():
            content_blocks.append(TextBlock(text=text))
        for attachment_id in ids:
            content_blocks.append(ImageBlock(attachment_id=attachment_id))

        user_message = Message(
            role="user", content=content_blocks, turn_id=turn_id
        )
        rows = await store.append_messages([user_message])
        # 与用户消息同一事务：消息里引用的图片从此属于本会话，后续回合才能加载到。
        await store.link_attachments(ids)
        await store.commit()

        if conversation.title == "新对话":
            title = text.strip()[:20] or "图片题目"
            await store.update_title(title)
            await store.commit()

        history = await store.load_history()

        state = (
            TutorState.from_json(conversation.state_json)
            if conversation.state_json
            else TutorState.idle()
        )

        problem: ProblemModel | None = None
        if state.problem_id is not None:
            problem_row = await store.load_problem(state.problem_id)
            if problem_row is not None:
                try:
                    problem = ProblemModel.model_validate(problem_row.model_json)
                except Exception:
                    logger.exception(
                        "题目模型无法解析：problem_id=%s", state.problem_id
                    )

        all_attachments = await store.list_attachments_for_conversation()
        known_ids = {int(row.id) for row in all_attachments}
        all_attachments.extend(
            row for row in attachment_rows if int(row.id) not in known_ids
        )
        image_loader = _build_image_loader(self._settings, all_attachments)

        ctx = ToolContext(
            store=store,
            settings=self._settings,
            config=self._config,
            reminders=self._reminders,
            provider=self._provider,
            user=user,
            conversation_id=conversation_id,
            turn_id=turn_id,
            student_text=text,
            attachment_ids=ids,
            user_message_id=rows[0].db_id,
            state=state,
            problem=problem,
            web=self._web,
        )
        guard = TurnGuard(
            self._config.policy.empty_step_retry_limit,
            reminder=self._reminders.text("guard_empty"),
            error_message=self._reminders.student_guard_error,
        )
        hooks = TutoringHooks(
            ctx=ctx,
            guard=guard,
            reminders=self._reminders,
            registry=self._registry,
        )
        runner = ToolRunnerAdapter(ctx, self._reminders, self._registry)
        failure_texts = _FailureTexts.from_reminders(self._reminders)

        async def call_model(step_request: StepRequest) -> AsyncIterator[ModelEvent]:
            system = build_system_prompt(
                self._config,
                grade=ctx.user.grade,
                grade_band=ctx.user.grade_band,
                state=ctx.state,
                problem=ctx.problem,
            )
            request = ModelRequest(
                model=self._settings.llm_model_tutor,
                system=system,
                messages=prepare_messages(step_request.messages),
                tools=step_request.tools,
                max_tokens=TUTOR_MAX_TOKENS,
                thinking=step_request.thinking,
                tool_choice=step_request.tool_choice,
                reasoning_turn_id=turn_id,
                image_loader=image_loader,
            )
            started = time.perf_counter()
            usage = Usage()
            try:
                async for event in self._provider.stream(request):
                    if isinstance(event, ModelUsage):
                        usage = event
                    yield event
            except Exception as exc:
                await ctx.log_llm_call(
                    purpose="tutor",
                    model=request.model,
                    prompt_version=TUTOR_SYSTEM_VERSION,
                    step=step_request.step,
                    thinking=step_request.thinking,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:500],
                )
                raise
            await ctx.log_llm_call(
                purpose="tutor",
                model=request.model,
                prompt_version=TUTOR_SYSTEM_VERSION,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                step=step_request.step,
                thinking=step_request.thinking,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        yield TurnStarted(turn_id=turn_id, phase=state.phase.value)

        visible_parts: list[str] = []
        try:
            async for event in query_loop(
                messages=history,
                call_model=call_model,
                tools=runner,
                hooks=hooks,
                max_steps=self._max_steps,
            ):
                if isinstance(event, TextDelta):
                    visible_parts.append(event.text)
                yield event
        except asyncio.CancelledError:
            await store.touch()
            await store.commit()
            yield TurnFinished("stopped")
            raise
        except LoopFailure as exc:
            logger.warning("回合被循环终止：%s", exc.reason)
            await store.touch()
            await store.commit()
            yield AgentError(failure_texts.for_reason(exc.reason, exc.message))
            yield TurnFinished("error")
            return
        except Exception:
            logger.exception("辅导回合执行失败")
            try:
                await store.rollback()
                await store.touch()
                await store.commit()
            except Exception:
                logger.exception("回滚后更新会话时间失败")
            yield AgentError(self._reminders.student_generic_error)
            yield TurnFinished("error")
            return

        if not visible_parts:
            # 模型这一回合没有给学生任何正文（例如工具连续失败后放弃）：
            # 不能让学生面对空白，给一句可操作的提示。
            yield AgentError(self._reminders.student_empty_reply)
            await store.touch()
            await store.commit()
            yield TurnFinished("error")
            return

        await store.touch()
        await store.commit()
        yield TurnFinished(
            status="complete", message_id=ctx.last_assistant_message_id
        )


__all__ = ["QueryEngine", "QueryEngineError", "ToolRunnerAdapter"]

"""单回合内的模型/工具循环。

每一步重新生成系统提示词（状态可能被上一步工具改变），调用模型，执行工具，
直到模型给出不含工具调用的回复或达到 `max_steps`。思考文本只保存、不下发。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from ai4edu.agent.content import (
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from ai4edu.agent.events import (
    AgentEvent,
    TextDelta,
    ThinkingState,
    ToolStatus,
)
from ai4edu.agent.hooks import DiagnosisGuard
from ai4edu.agent.messages import AgentMessage
from ai4edu.llm.format import ImageLoader, to_openai_messages
from ai4edu.llm.stream import (
    StreamEnd,
    TextDelta as LLMTextDelta,
    ThinkingDelta,
    ToolCall,
    ToolCallsReady,
    Usage,
    stream_chat,
)
from ai4edu.storage.repos import messages as messages_repo
from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tools.registry import to_openai_tools, tools_for
from ai4edu.tutoring.prompt_builder import build_tutor_system_prompt

logger = logging.getLogger(__name__)

_GUARD_ERROR = "老师刚才走神了，请再发一次你的回答。"
_MAX_STEPS_ERROR = "老师需要再想一想，请稍后再试。"
_ALREADY_SENT_REMINDER = (
    "（系统提醒：你在本回合已经对学生说过上面那段话，学生已经看到。"
    "不要重复或改写它；如果没有新的内容要补充，就不要再输出正文。）"
)


class AgentLoopFailure(Exception):
    """循环无法继续，需要以 error 状态结束回合。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _parse_arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    if not raw.strip():
        return {}, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"工具参数不是合法 JSON：{exc}"
    if not isinstance(value, dict):
        return None, "工具参数必须是 JSON 对象"
    return value, None


async def _append_assistant(
    ctx: ToolContext,
    blocks: list[Any],
    *,
    history: list[AgentMessage],
) -> int | None:
    if not blocks:
        return None
    message = AgentMessage(
        role="assistant", content=blocks, turn_id=ctx.turn_id
    )
    rows = await messages_repo.append_messages(
        ctx.db, ctx.conversation_id, [message.to_append_dict()]
    )
    await ctx.db.commit()
    message.db_id = rows[0].id
    history.append(message)
    ctx.last_assistant_message_id = rows[0].id
    return rows[0].id


async def _append_tool_result(
    ctx: ToolContext,
    block: ToolResultBlock,
    *,
    history: list[AgentMessage],
) -> None:
    message = AgentMessage(role="tool", content=[block], turn_id=ctx.turn_id)
    rows = await messages_repo.append_messages(
        ctx.db, ctx.conversation_id, [message.to_append_dict()]
    )
    await ctx.db.commit()
    message.db_id = rows[0].id
    history.append(message)


async def _execute_tool(
    call: ToolCall,
    tool: BaseTool | None,
    arguments: dict[str, Any] | None,
    argument_error: str | None,
    ctx: ToolContext,
) -> ToolResult:
    if tool is None:
        return ToolResult(
            content=f"未知工具 {call.name}，请只使用提供的工具。",
            is_error=True,
            status_label="工具不可用",
        )
    if arguments is None:
        return ToolResult(
            content=f"{argument_error}。请重新调用 {call.name} 并给出合法 JSON 参数。",
            is_error=True,
            status_label="参数错误",
        )
    try:
        return await tool.execute(arguments, ctx)
    except Exception:
        logger.exception("工具 %s 执行失败", call.name)
        return ToolResult(
            content=f"工具 {call.name} 执行失败，请换一种方式继续。",
            is_error=True,
            status_label="工具出错",
        )


async def agent_loop(
    *,
    client: AsyncOpenAI,
    model: str,
    history: list[AgentMessage],
    ctx: ToolContext,
    guard: DiagnosisGuard,
    image_loader: ImageLoader,
    max_steps: int = 8,
) -> AsyncIterator[AgentEvent]:
    """运行一个学生回合。生成器结束时表示回合正常完成。"""

    reminder: AgentMessage | None = None
    analyzed_this_turn = False

    for _step in range(max_steps):
        request_messages = list(history)
        if reminder is not None:
            request_messages.append(reminder)

        system_prompt = build_tutor_system_prompt(
            ctx.config,
            grade=ctx.user.grade,
            grade_band=ctx.user.grade_band,
            state=ctx.state,
            problem=ctx.problem,
        )
        api_messages = [
            {"role": "system", "content": system_prompt},
            *to_openai_messages(
                request_messages,
                image_loader=image_loader,
                include_reasoning_for_turn=ctx.turn_id,
            ),
        ]

        tools = tools_for(ctx.state.phase)
        if analyzed_this_turn:
            # 本回合刚分析完新题：学生还没有针对子任务作答，不能诊断。
            tools = [tool for tool in tools if tool.name != "record_diagnosis"]
        tool_map = {tool.name: tool for tool in tools}
        started = time.perf_counter()
        thinking_parts: list[str] = []
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        usage = Usage()
        thinking_active = False
        content_started = False

        try:
            async for event in stream_chat(
                client,
                model=model,
                messages=api_messages,
                tools=to_openai_tools(tools),
            ):
                if isinstance(event, ThinkingDelta):
                    thinking_parts.append(event.text)
                    if not thinking_active:
                        thinking_active = True
                        yield ThinkingState(True)
                elif isinstance(event, LLMTextDelta):
                    if not content_started:
                        content_started = True
                        yield ThinkingState(False)
                    if guard.text_delta(event.text):
                        text_parts.append(event.text)
                        yield TextDelta(event.text)
                elif isinstance(event, ToolCallsReady):
                    tool_calls = list(event.calls)
                elif isinstance(event, StreamEnd):
                    usage = event.usage
        except asyncio.CancelledError:
            # 已下发的正文与思考先落库，避免停止生成时丢失。
            blocks: list[Any] = []
            if thinking_parts:
                blocks.append(ThinkingBlock(text="".join(thinking_parts)))
            if text_parts:
                blocks.append(TextBlock(text="".join(text_parts)))
            if blocks:
                await _append_assistant(ctx, blocks, history=history)
            raise
        except Exception as exc:
            await ctx.log_llm_call(
                purpose="tutor",
                model=model,
                prompt_version=ctx.config.tutor_system_version,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc)[:500],
            )
            raise

        await ctx.log_llm_call(
            purpose="tutor",
            model=model,
            prompt_version=ctx.config.tutor_system_version,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

        if tool_calls and not content_started:
            yield ThinkingState(False)

        # 工具调用参数先解析；非法参数会作为错误结果回给模型。
        prepared: list[tuple[ToolCall, BaseTool | None, dict[str, Any] | None, str | None]] = []
        for call in tool_calls:
            arguments, error = _parse_arguments(call.arguments)
            prepared.append((call, tool_map.get(call.name), arguments, error))

        assistant_blocks: list[Any] = []
        if thinking_parts:
            assistant_blocks.append(ThinkingBlock(text="".join(thinking_parts)))
        if text_parts:
            assistant_blocks.append(TextBlock(text="".join(text_parts)))
        for call, _, arguments, _ in prepared:
            assistant_blocks.append(
                ToolUseBlock(
                    id=call.id,
                    name=call.name,
                    input=arguments if arguments is not None else {},
                )
            )

        if tool_calls:
            # 先保存 assistant 消息，再逐个执行并保存结果；中途停止也不会丢调用。
            await _append_assistant(ctx, assistant_blocks, history=history)
            answered_directly = False
            for call, tool, arguments, argument_error in prepared:
                label = tool.running_label if tool is not None else call.name
                yield ToolStatus(call.name, label, "running")

                result = await _execute_tool(
                    call, tool, arguments, argument_error, ctx
                )
                status = "error" if result.is_error else "done"
                result_label = result.status_label or ("出错" if result.is_error else "完成")
                yield ToolStatus(call.name, result_label, status)

                await _append_tool_result(
                    ctx,
                    ToolResultBlock(
                        tool_use_id=call.id,
                        content=result.content,
                        is_error=result.is_error,
                        status_label=result.status_label,
                    ),
                    history=history,
                )
                guard.on_tool_result(call.name, result.is_error)
                if call.name == "answer_directly" and not result.is_error:
                    answered_directly = True
                if call.name == "analyze_problem" and not result.is_error:
                    analyzed_this_turn = True

            if answered_directly:
                # 回复已经由工具确认并暂存，不再给模型重复或寒暄的机会；
                # 引擎会在回合结束时把 pending_reply 发给学生。
                return

            reminder = None
            if text_parts:
                # 本步已经有正文发给学生，下一步只允许补充，不允许重写。
                reminder = AgentMessage(
                    role="user",
                    content=[TextBlock(text=_ALREADY_SENT_REMINDER)],
                    turn_id=None,
                )
        else:
            await _append_assistant(ctx, assistant_blocks, history=history)

        decision = guard.finish_step(has_tool_calls=bool(tool_calls))
        if decision.action == "error":
            raise AgentLoopFailure(decision.error_message or _GUARD_ERROR)
        if decision.action == "retry":
            reminder = AgentMessage(
                role="user",
                content=[TextBlock(text=decision.reminder or "")],
                turn_id=None,
            )
            continue
        if not tool_calls:
            return

    raise AgentLoopFailure(_MAX_STEPS_ERROR)


__all__ = ["AgentLoopFailure", "agent_loop"]

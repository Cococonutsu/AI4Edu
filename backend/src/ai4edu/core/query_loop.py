"""无状态的模型/工具循环（`docs/architecture.md` 第 2 节）。

本模块只依赖 `models/`、`core/events.py` 和传入的参数：不导入 `api/`、
`session/`、`storage/`、`tutoring/`、`prompts/`、`tools.registry`，源码中
不出现任何具体工具名。持久化由钩子完成，模型调用与计量由 `call_model`
完成，工具执行由 `ToolRunner` 完成——三者都从参数传入。

每一步：`hooks.before_step()` 决定本步的工具列表、thinking、tool_choice →
`call_model` → 收集事件（思考只发 `ThinkingState`，正文即时下发）→ 组装 assistant 消息并交给
`hooks.on_message()` → 执行工具（`ToolStatus` 事件前后各一个）→ 每个结果
组成 tool 消息并持久化 → `hooks.after_tool()` 可以要求结束回合 →
`hooks.after_step()` 决定继续、重试（带提醒）还是报错。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, TypeAlias

from ai4edu.core.events import (
    AgentEvent,
    TextDelta,
    ThinkingState,
    ToolDisplay,
    ToolStatus,
)
from ai4edu.utils.errors import LoopFailure, ProviderError
from ai4edu.models.contracts import (
    ModelEvent,
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
    ThinkingMode,
    ToolChoice,
    ToolSchema,
    ToolUseReady,
)
from ai4edu.models.content import (
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from ai4edu.models.messages import Message


@dataclass
class StepRequest:
    step: int
    messages: list[Message]
    tools: list[ToolSchema]
    thinking: ThinkingMode
    tool_choice: ToolChoice
    # 本步的输出上限；None 用引擎默认。截断恢复时由循环提升（见
    # `_ESCALATED_MAX_TOKENS`）。
    max_tokens: int | None = None


CallModel = Callable[[StepRequest], AsyncIterator[ModelEvent]]


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False
    status_label: str = ""
    # 允许下发给浏览器的展示数据（由工具自己生成，循环只负责转发）。
    display: dict[str, Any] | None = None


class ToolRunner(Protocol):
    """列出当前可用的工具并执行调用。"""

    def schemas(self) -> list[ToolSchema]: ...

    def running_label(self, name: str) -> str: ...

    async def execute(
        self, name: str, arguments: dict[str, Any] | None, input_error: str | None
    ) -> ToolOutcome: ...


@dataclass
class StepPlan:
    tools: list[ToolSchema]
    thinking: ThinkingMode
    tool_choice: ToolChoice


@dataclass
class StepDecision:
    action: Literal["continue", "retry", "end", "error"]
    # 下一步请求要附加的临时提醒（不持久化、不留在历史里）。
    reminder: Message | None = None
    error_text: str | None = None


class LoopHooks(Protocol):
    """注入循环的业务规则；实现方持有持久化与提醒文字。"""

    def before_step(self, step: int) -> StepPlan: ...

    async def on_message(self, message: Message) -> None: ...

    def after_tool(self, name: str, *, is_error: bool) -> bool: ...

    def after_step(self, *, has_tool_calls: bool, sent_text: bool) -> StepDecision: ...

    def on_truncated(self) -> Message:
        """正文被长度截断、学生已看到部分内容时，返回"继续说完"的提醒。"""
        ...



_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0)

# 输出被长度截断（finish_reason == "length"）时的恢复：逐级加大输出额度，
# 最多恢复两次；额度用尽后按普通结果处理（对齐 cc 的 escalate 策略）。
_ESCALATED_MAX_TOKENS: tuple[int, ...] = (32768, 65536)


async def query_loop(
    *,
    messages: list[Message],
    call_model: CallModel,
    tools: ToolRunner,
    hooks: LoopHooks,
    max_steps: int = 8,
) -> AsyncIterator[AgentEvent]:
    """运行一个学生回合。生成器正常结束表示回合完成。"""

    reminder: Message | None = None
    # 截断恢复状态：当前输出额度（None=引擎默认）与已用掉的恢复次数。
    current_max_tokens: int | None = None
    length_recoveries = 0

    for step in range(1, max_steps + 1):
        plan = hooks.before_step(step)
        request_messages = list(messages)
        if reminder is not None:
            request_messages.append(reminder)
        reminder = None
        step_request = StepRequest(
            step=step,
            messages=request_messages,
            tools=plan.tools,
            thinking=plan.thinking,
            tool_choice=plan.tool_choice,
            max_tokens=current_max_tokens,
        )

        thinking_parts: list[str] = []
        text_parts: list[str] = []
        tool_uses: list[Any] = []
        thinking_active = False
        content_started = False

        attempts = 0
        truncated = False
        while True:
            try:
                async for event in call_model(step_request):
                    if isinstance(event, ModelThinkingDelta):
                        thinking_parts.append(event.text)
                        if not thinking_active:
                            thinking_active = True
                            yield ThinkingState(True)
                    elif isinstance(event, ModelTextDelta):
                        if not content_started:
                            content_started = True
                            yield ThinkingState(False)
                        text_parts.append(event.text)
                        yield TextDelta(event.text)
                    elif isinstance(event, ToolUseReady):
                        tool_uses = list(event.calls)
                    elif isinstance(event, ModelStreamEnd):
                        truncated = event.finish_reason == "length"
                    # ModelUsage 的计量由 call_model 侧记录。
                # 输出被截断且这一步什么都没拿到（没有正文、工具参数不完整）：
                # 学生什么都没看到，丢弃这次尝试、加大输出额度原样重试，
                # 不占步数预算。
                usable_calls = [use for use in tool_uses if use.input is not None]
                if truncated and not text_parts and not usable_calls:
                    if length_recoveries < len(_ESCALATED_MAX_TOKENS):
                        length_recoveries += 1
                        current_max_tokens = _ESCALATED_MAX_TOKENS[
                            length_recoveries - 1
                        ]
                        step_request = replace(
                            step_request, max_tokens=current_max_tokens
                        )
                        thinking_parts = []
                        text_parts = []
                        tool_uses = []
                        thinking_active = False
                        content_started = False
                        truncated = False
                        continue
                break
            except ProviderError as exc:
                # 已有正文下发时不能原步重试（会重复发给学生），直接结束。
                can_retry = (
                    exc.recoverable
                    and attempts < len(_RETRY_DELAYS)
                    and not text_parts
                )
                if can_retry:
                    await asyncio.sleep(_RETRY_DELAYS[attempts])
                    attempts += 1
                    continue
                if exc.recoverable:
                    raise LoopFailure("network_error") from exc
                raise LoopFailure("provider_error") from exc
            except asyncio.CancelledError:
                # 已产生的思考与正文先落库，避免停止生成时丢失。
                blocks: list[Any] = []
                if thinking_parts:
                    blocks.append(ThinkingBlock(text="".join(thinking_parts)))
                if text_parts:
                    blocks.append(TextBlock(text="".join(text_parts)))
                if blocks:
                    partial = Message(role="assistant", content=blocks)
                    messages.append(partial)
                    await hooks.on_message(partial)
                raise

        if tool_uses and not content_started:
            yield ThinkingState(False)

        assistant_blocks: list[Any] = []
        if thinking_parts:
            assistant_blocks.append(
                ThinkingBlock(text="".join(thinking_parts))
            )
        if text_parts:
            assistant_blocks.append(TextBlock(text="".join(text_parts)))
        for use in tool_uses:
            assistant_blocks.append(
                ToolUseBlock(
                    id=use.id,
                    name=use.name,
                    input=use.input if use.input is not None else {},
                )
            )

        if assistant_blocks:
            assistant = Message(role="assistant", content=assistant_blocks)
            messages.append(assistant)
            await hooks.on_message(assistant)

        if tool_uses:
            for use in tool_uses:
                label = tools.running_label(use.name)
                yield ToolStatus(use.name, label, "running")

                outcome = await tools.execute(use.name, use.input, use.input_error)
                status = "error" if outcome.is_error else "done"
                result_label = outcome.status_label or (
                    "出错" if outcome.is_error else "完成"
                )
                yield ToolStatus(use.name, result_label, status)

                tool_message = Message(
                    role="tool",
                    content=[
                        ToolResultBlock(
                            tool_use_id=use.id,
                            content=outcome.content,
                            is_error=outcome.is_error,
                            status_label=outcome.status_label,
                            display=outcome.display,
                        )
                    ],
                )
                messages.append(tool_message)
                await hooks.on_message(tool_message)
                if outcome.display is not None:
                    yield ToolDisplay(
                        kind=str(outcome.display.get("kind") or "display"),
                        payload=outcome.display,
                    )
                if hooks.after_tool(use.name, is_error=outcome.is_error):
                    # 回复已由工具确认发送，不给模型重复或寒暄的机会。
                    return

        decision = hooks.after_step(
            has_tool_calls=bool(tool_uses), sent_text=bool(text_parts)
        )
        if decision.action == "error":
            raise LoopFailure("guard", decision.error_text)
        reminder = decision.reminder
        if decision.action == "retry":
            continue
        if truncated and length_recoveries < len(_ESCALATED_MAX_TOKENS):
            # 截断恢复：本回合后续调用逐级加大输出额度（对齐 cc 的 escalate）。
            length_recoveries += 1
            current_max_tokens = _ESCALATED_MAX_TOKENS[length_recoveries - 1]
            if not tool_uses and text_parts:
                # 正文被截断、学生已看到部分内容：不结束回合，
                # 提醒模型从中断处继续说完（提醒不持久化）。
                reminder = hooks.on_truncated()
                continue
        if not tool_uses:
            return

    raise LoopFailure("max_steps")


__all__ = [
    "CallModel",
    "LoopFailure",
    "LoopHooks",
    "StepDecision",
    "StepPlan",
    "StepRequest",
    "ToolOutcome",
    "ToolRunner",
    "query_loop",
]

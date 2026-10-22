"""`query_loop` 的 Provider 错误重试与结束路径。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

import ai4edu.core.query_loop as query_loop_module
from ai4edu.core.events import TextDelta
from ai4edu.core.query_loop import (
    LoopFailure,
    StepDecision,
    StepPlan,
    ToolOutcome,
    query_loop,
)
from ai4edu.models.contracts import (
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
)
from ai4edu.utils.errors import ProviderError
from ai4edu.models.content import TextBlock
from ai4edu.models.messages import Message

pytestmark = pytest.mark.asyncio


class _Hooks:
    """最小钩子：透传正文，工具步后结束。"""

    def before_step(self, step: int) -> StepPlan:
        return StepPlan(tools=[], thinking="on", tool_choice="auto")

    async def on_message(self, message: Message) -> None:
        return None

    def after_tool(self, name: str, *, is_error: bool) -> bool:
        return False

    def after_step(self, *, has_tool_calls: bool, sent_text: bool) -> StepDecision:
        return StepDecision("continue")

    def on_truncated(self) -> Message:
        return Message(role="user", content=[TextBlock(text="（继续说完）")])


class _Runner:
    def schemas(self) -> list[Any]:
        return []

    def running_label(self, name: str) -> str:
        return name

    async def execute(self, name, arguments, input_error) -> ToolOutcome:
        return ToolOutcome(content="ok")


def _script_call_model(script: list[Any]):
    """按脚本产出事件的 call_model。

    脚本元素是：事件列表（正常一步）、异常（该步调用失败），或
    `(事件列表, 异常)` 元组（先产出事件、再失败，模拟流中断）。
    """

    async def call_model(step_request) -> AsyncIterator[Any]:
        assert script, "收到了多余的模型调用"
        item = script.pop(0)
        if isinstance(item, tuple):
            events, error = item
            for event in events:
                yield event
            raise error
        if isinstance(item, BaseException):
            raise item
        for event in item:
            yield event

    return call_model


async def _run(script: list[Any]) -> list[Any]:
    events: list[Any] = []
    generator = query_loop(
        messages=[Message(role="user", content=[TextBlock(text="题目")])],
        call_model=_script_call_model(script),
        tools=_Runner(),
        hooks=_Hooks(),
        max_steps=8,
    )
    async for event in generator:
        events.append(event)
    return events


@pytest.fixture
def no_sleep(monkeypatch):
    async def instant_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(query_loop_module.asyncio, "sleep", instant_sleep)


async def test_recoverable_error_is_retried_and_succeeds(no_sleep):
    events = await _run(
        [
            ProviderError("网络抖动", recoverable=True),
            [ModelTextDelta(text="好了")],
        ]
    )

    assert [event.text for event in events if isinstance(event, TextDelta)] == ["好了"]


async def test_retry_uses_backoff_delays(no_sleep, monkeypatch):
    delays: list[float] = []

    async def recording_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(query_loop_module.asyncio, "sleep", recording_sleep)

    await _run(
        [
            ProviderError("第一次失败", recoverable=True),
            ProviderError("第二次失败", recoverable=True),
            [ModelTextDelta(text="最终成功")],
        ]
    )

    assert delays == [1.0, 2.0]


async def test_unrecoverable_error_fails_immediately(no_sleep):
    with pytest.raises(LoopFailure) as info:
        await _run([ProviderError("密钥无效", recoverable=False)])

    assert info.value.reason == "provider_error"


async def test_retries_exhausted_ends_with_network_error(no_sleep):
    with pytest.raises(LoopFailure) as info:
        await _run(
            [
                ProviderError("一", recoverable=True),
                ProviderError("二", recoverable=True),
                ProviderError("三", recoverable=True),
            ]
        )

    assert info.value.reason == "network_error"


async def test_no_retry_after_visible_text(no_sleep):
    """正文已经下发给学生后不能原步重试，否则学生会看到重复内容。"""

    with pytest.raises(LoopFailure) as info:
        await _run(
            [
                ([ModelTextDelta(text="写了一半")], ProviderError("断了", recoverable=True)),
            ]
        )

    assert info.value.reason == "network_error"


async def test_max_steps_raises_loop_failure(no_sleep):
    from ai4edu.models.contracts import ToolUse, ToolUseReady

    steps = [
        [ToolUseReady(calls=[ToolUse(id=f"c{n}", name="record_diagnosis", input={})])]
        for n in range(8)
    ]

    with pytest.raises(LoopFailure) as info:
        await _run(steps)

    assert info.value.reason == "max_steps"


async def test_pure_truncation_is_retried_with_escalated_max_tokens():
    """截断时这一步什么都没拿到（只有思考/坏参数）：加大额度原步重试。"""

    requests_seen: list[Any] = []
    script: list[Any] = [
        [ModelThinkingDelta(text="想了一半"), ModelStreamEnd(finish_reason="length")],
        [ModelTextDelta(text="完整的回答"), ModelStreamEnd(finish_reason="stop")],
    ]

    async def call_model(step_request) -> AsyncIterator[Any]:
        requests_seen.append(step_request)
        for event in script.pop(0):
            yield event

    events = []
    generator = query_loop(
        messages=[Message(role="user", content=[TextBlock(text="题目")])],
        call_model=call_model,
        tools=_Runner(),
        hooks=_Hooks(),
        max_steps=8,
    )
    async for event in generator:
        events.append(event)

    # 第一次用默认额度，第二次已升级到 32768，且仍是第 1 步（不占步数）。
    assert requests_seen[0].max_tokens is None
    assert requests_seen[1].max_tokens == 32768
    assert [r.step for r in requests_seen] == [1, 1]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "完整的回答"


async def test_truncated_text_continues_after_reminder():
    """正文被截断、学生已看到部分：追加续写提醒继续，不结束回合。"""

    requests_seen: list[Any] = []
    script: list[Any] = [
        [ModelTextDelta(text="前半段"), ModelStreamEnd(finish_reason="length")],
        [ModelTextDelta(text="，后半段"), ModelStreamEnd(finish_reason="stop")],
    ]

    async def call_model(step_request) -> AsyncIterator[Any]:
        requests_seen.append(step_request)
        for event in script.pop(0):
            yield event

    events = []
    generator = query_loop(
        messages=[Message(role="user", content=[TextBlock(text="题目")])],
        call_model=call_model,
        tools=_Runner(),
        hooks=_Hooks(),
        max_steps=8,
    )
    async for event in generator:
        events.append(event)

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "前半段，后半段"
    # 第二次请求：额度已升级，且最后一条消息是"继续说完"的提醒。
    assert requests_seen[1].max_tokens == 32768
    last = requests_seen[1].messages[-1]
    assert last.role == "user"
    assert "继续说完" in last.content[0].text


async def test_length_recovery_is_capped():
    """恢复额度用尽后照常结束回合，不会无限续写。"""

    requests_seen: list[Any] = []

    async def call_model(step_request) -> AsyncIterator[Any]:
        requests_seen.append(step_request)
        yield ModelTextDelta(text="还在写")
        yield ModelStreamEnd(finish_reason="length")

    events = []
    generator = query_loop(
        messages=[Message(role="user", content=[TextBlock(text="题目")])],
        call_model=call_model,
        tools=_Runner(),
        hooks=_Hooks(),
        max_steps=8,
    )
    async for event in generator:
        events.append(event)

    # 一次原始调用 + 两次续写恢复，之后接受截断、正常结束。
    assert len(requests_seen) == 3
    assert [r.max_tokens for r in requests_seen] == [None, 32768, 65536]

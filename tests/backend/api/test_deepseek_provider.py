"""`DeepSeekProvider`：参数防护、流解析与异常映射。"""

from __future__ import annotations

import json

import httpx
import openai
import pytest

from ai4edu.api.base import ModelRequest, ProviderError, ToolSchema
from ai4edu.api.deepseek import DeepSeekProvider
from ai4edu.core.events import (
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
    ModelUsage,
    ToolUseReady,
)
from ai4edu.models.content import TextBlock
from ai4edu.models.messages import Message
from fakes import FakeLLMClient, FakeResponse

pytestmark = pytest.mark.asyncio


def _request(**overrides) -> ModelRequest:
    values: dict = {
        "model": "deepseek-flash",
        "system": "你是老师",
        "messages": [Message(role="user", content=[TextBlock(text="算一下")])],
    }
    values.update(overrides)
    return ModelRequest(**values)


def _tools() -> list[ToolSchema]:
    return [
        ToolSchema(
            name="record_diagnosis",
            description="核对",
            input_schema={"type": "object"},
        )
    ]


async def test_thinking_off_sends_extra_body_and_on_does_not():
    client = FakeLLMClient([FakeResponse(text=["好"]), FakeResponse(text=["好"])])
    provider = DeepSeekProvider(client)

    async for _ in provider.stream(_request(thinking="off")):
        pass
    async for _ in provider.stream(_request(thinking="on")):
        pass

    assert client.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in client.calls[1]


async def test_tools_and_tool_choice_passthrough():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = DeepSeekProvider(client)

    async for _ in provider.stream(
        _request(thinking="off", tools=_tools(), tool_choice="required")
    ):
        pass

    assert client.calls[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "record_diagnosis",
                "description": "核对",
                "parameters": {"type": "object"},
            },
        }
    ]
    # 关闭思考时 DeepSeek 允许 required，原样透传。
    assert client.calls[0]["tool_choice"] == "required"


async def test_thinking_on_downgrades_required_tool_choice_to_auto():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = DeepSeekProvider(client)

    async for _ in provider.stream(
        _request(thinking="on", tools=_tools(), tool_choice="required")
    ):
        pass

    # 思考模式下 required 会 400，实际发出的是 auto。
    assert client.calls[0]["tool_choice"] == "auto"
    assert client.calls[0]["tools"][0]["function"]["name"] == "record_diagnosis"


async def test_stream_assembles_reasoning_text_and_tool_arguments():
    arguments = '{"operations": [{"kind": "equal", "left": "1+1", "right": "2"}]}'
    client = FakeLLMClient(
        [
            FakeResponse(
                thinking=["先想", "一下"],
                text=["你好", "！"],
                tool_calls=[("call_1", "record_diagnosis", arguments)],
                input_tokens=13,
                output_tokens=17,
            )
        ]
    )
    provider = DeepSeekProvider(client)

    events = [event async for event in provider.stream(_request())]

    assert [type(event) for event in events] == [
        ModelThinkingDelta,
        ModelThinkingDelta,
        ModelTextDelta,
        ModelTextDelta,
        ToolUseReady,
        ModelUsage,
        ModelStreamEnd,
    ]
    thinking = "".join(
        event.text
        for event in events
        if isinstance(event, ModelThinkingDelta)
    )
    text = "".join(
        event.text for event in events if isinstance(event, ModelTextDelta)
    )
    tool_events = [event for event in events if isinstance(event, ToolUseReady)]
    usage_events = [event for event in events if isinstance(event, ModelUsage)]
    end = events[-1]

    assert thinking == "先想一下"
    assert text == "你好！"
    assert len(tool_events) == 1
    call = tool_events[0].calls[0]
    assert call.id == "call_1"
    assert call.name == "record_diagnosis"
    assert call.input == json.loads(arguments)
    assert call.input_error is None
    assert usage_events[0].input_tokens == 13
    assert usage_events[0].output_tokens == 17
    assert isinstance(end, ModelStreamEnd)
    assert end.finish_reason == "tool_calls"


def _openai_status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(f"HTTP {status_code}", response=response, body=None)


@pytest.mark.parametrize(
    "exc,recoverable",
    [
        (_openai_status_error(429), True),
        (_openai_status_error(500), True),
        (_openai_status_error(400), False),
        (
            openai.APIConnectionError(
                request=httpx.Request("POST", "https://api.deepseek.com")
            ),
            True,
        ),
    ],
)
async def test_error_mapping_to_provider_error(exc, recoverable):
    client = FakeLLMClient([exc])
    provider = DeepSeekProvider(client)

    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(_request()):
            pass

    assert info.value.recoverable is recoverable

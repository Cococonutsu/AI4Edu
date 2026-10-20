"""`GLMProvider`：内部消息转译、流解析、thinking 开关与异常映射。"""

from __future__ import annotations

import json

import httpx
import openai
import pytest

from ai4edu.api.base import (
    ModelRequest,
    ProviderError,
    ToolSchema,
)
from ai4edu.api.glm import GLMProvider
from ai4edu.api.json_util import JsonParseError, complete_json, extract_json_object
from ai4edu.models.content import (
    ImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from ai4edu.models.messages import Message
from fakes import FakeLLMClient, FakeResponse

pytestmark = pytest.mark.asyncio


def _request(**overrides) -> ModelRequest:
    values: dict = {
        "model": "test-model",
        "system": "你是老师",
        "messages": [Message(role="user", content=[TextBlock(text="算一下")])],
    }
    values.update(overrides)
    return ModelRequest(**values)


async def test_stream_assembles_fragmented_tool_arguments():
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
    provider = GLMProvider(client)

    events = [event async for event in provider.stream(_request())]

    from ai4edu.core.events import (
        ModelStreamEnd,
        ModelTextDelta,
        ModelThinkingDelta,
        ModelUsage,
        ToolUseReady,
    )

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
    assert usage_events and usage_events[0].input_tokens == 13
    assert usage_events[0].output_tokens == 17
    assert isinstance(end, ModelStreamEnd)
    assert end.finish_reason == "tool_calls"


async def test_stream_invalid_tool_arguments_become_input_error():
    client = FakeLLMClient(
        [FakeResponse(tool_calls=[("call_1", "record_diagnosis", "不是 JSON")])]
    )
    provider = GLMProvider(client)

    events = [event async for event in provider.stream(_request())]

    from ai4edu.core.events import ToolUseReady

    ready = [event for event in events if isinstance(event, ToolUseReady)][0]
    assert ready.calls[0].input is None
    assert ready.calls[0].input_error is not None


async def test_wire_format_images_before_text_and_system_first():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = GLMProvider(client)

    async for _ in provider.stream(
        _request(
            messages=[
                Message(
                    role="user",
                    content=[
                        TextBlock(text="看这张图"),
                        ImageBlock(attachment_id=5),
                    ],
                )
            ],
            image_loader=lambda attachment_id: ("image/png", b"PNGDATA"),
        )
    ):
        pass

    messages = client.messages(0)
    assert messages[0] == {"role": "system", "content": "你是老师"}
    content = messages[1]["content"]
    assert [part["type"] for part in content] == ["image_url", "text"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "看这张图"}


async def test_wire_format_tool_calls_and_tool_role_messages():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = GLMProvider(client)

    async for _ in provider.stream(
        _request(
            messages=[
                Message(role="user", content=[TextBlock(text="核对")]),
                Message(
                    role="assistant",
                    content=[
                        ThinkingBlock(text="想一想"),
                        TextBlock(text="我核对一下"),
                        ToolUseBlock(
                            id="call_9",
                            name="record_diagnosis",
                            input={"operations": []},
                        ),
                    ],
                    turn_id="turn-1",
                ),
                Message(
                    role="tool",
                    content=[
                        ToolResultBlock(tool_use_id="call_9", content="都对")
                    ],
                ),
            ],
            reasoning_turn_id="turn-1",
        )
    ):
        pass

    messages = client.messages(0)
    assert messages[2] == {
        "role": "assistant",
        "content": "我核对一下",
        "reasoning_content": "想一想",
        "tool_calls": [
            {
                "id": "call_9",
                "type": "function",
                "function": {
                    "name": "record_diagnosis",
                    "arguments": '{"operations": []}',
                },
            }
        ],
    }
    assert messages[3] == {
        "role": "tool",
        "tool_call_id": "call_9",
        "content": "都对",
    }


async def test_reasoning_only_returned_for_current_turn():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = GLMProvider(client)

    async for _ in provider.stream(
        _request(
            messages=[
                Message(role="user", content=[TextBlock(text="上一回合")]),
                Message(
                    role="assistant",
                    content=[
                        ThinkingBlock(text="旧思考"),
                        TextBlock(text="旧回复"),
                    ],
                    turn_id="turn-old",
                ),
                Message(
                    role="user", content=[TextBlock(text="这一回合")]
                ),
            ],
            reasoning_turn_id="turn-new",
        )
    ):
        pass

    assistant_wire = client.messages(0)[2]
    assert assistant_wire["content"] == "旧回复"
    assert "reasoning_content" not in assistant_wire


async def test_empty_system_omits_system_message():
    client = FakeLLMClient([FakeResponse(text=["好"])])
    provider = GLMProvider(client)

    async for _ in provider.stream(_request(system="")):
        pass

    assert client.messages(0)[0]["role"] == "user"


async def test_thinking_off_sends_extra_body_and_on_does_not():
    client = FakeLLMClient([FakeResponse(text=["好"]), FakeResponse(text=["好"])])
    provider = GLMProvider(client)

    async for _ in provider.stream(_request(thinking="off")):
        pass
    async for _ in provider.stream(_request(thinking="on")):
        pass

    assert client.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in client.calls[1]


async def test_tools_and_tool_choice_mapping():
    client = FakeLLMClient([FakeResponse(text=["好"]), FakeResponse(text=["好"])])
    provider = GLMProvider(client)
    tools = [
        ToolSchema(
            name="record_diagnosis", description="核对", input_schema={"type": "object"}
        )
    ]

    async for _ in provider.stream(_request(tools=tools, tool_choice="required")):
        pass
    async for _ in provider.stream(_request()):
        pass

    assert client.calls[0]["tool_choice"] == "required"
    assert client.calls[0]["tools"][0]["function"]["name"] == "record_diagnosis"
    assert "tools" not in client.calls[1]
    assert "tool_choice" not in client.calls[1]


async def test_complete_extracts_text_and_usage():
    client = FakeLLMClient([FakeResponse(content='{"answer": 42}')])
    provider = GLMProvider(client)

    response = await provider.complete(_request())

    assert response.text == '{"answer": 42}'
    assert response.usage.input_tokens == 11


async def test_complete_json_extracts_object_from_fence_and_prose():
    client = FakeLLMClient(
        [FakeResponse(content='先说明一下：\n```json\n{"answer": 42}\n```\n以上。')]
    )
    provider = GLMProvider(client)

    data, response = await complete_json(provider, _request())

    assert data == {"answer": 42}
    assert response.usage.input_tokens > 0


async def test_complete_json_raises_when_no_json_found():
    client = FakeLLMClient([FakeResponse(content="这里没有 JSON")])
    provider = GLMProvider(client)

    with pytest.raises(JsonParseError):
        await complete_json(provider, _request())


async def test_extract_json_object_returns_none_for_garbage():
    assert extract_json_object("完全没有花括号") is None


def _openai_status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.test/v4/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(f"HTTP {status_code}", response=response, body=None)


@pytest.mark.parametrize(
    "exc,recoverable",
    [
        (openai.APIConnectionError(request=httpx.Request("POST", "https://api.test")), True),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://api.test")), True),
        (_openai_status_error(429), True),
        (_openai_status_error(503), True),
        (_openai_status_error(401), False),
        (RuntimeError("别的错"), False),
    ],
)
async def test_error_mapping_to_provider_error(exc, recoverable):
    client = FakeLLMClient([exc])
    provider = GLMProvider(client)

    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(_request()):
            pass

    assert info.value.recoverable is recoverable

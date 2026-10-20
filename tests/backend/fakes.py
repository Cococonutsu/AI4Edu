"""测试用的模拟模型客户端与模拟 Provider。

`FakeLLMClient` 只实现代码实际用到的
`client.chat.completions.create(**kwargs)`，按脚本顺序返回流式或非流式响应，
并记录每次调用的参数（用来断言厂商请求格式，配合 `GLMProvider` 使用）。
`FakeProvider` 直接按脚本产出 `ModelEvent` / `ModelResponse`，并记录收到的
`ModelRequest`（用来断言循环与引擎的行为）。
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from ai4edu.api.base import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ToolUse,
    Usage,
)
from ai4edu.core.events import (
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
    ModelUsage,
    ToolUseReady,
)


def _as_parts(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


@dataclass
class FakeResponse:
    """一次调用的返回描述。

    - 流式（`content is None`）：`thinking` / `text` 是分片列表，
      `tool_calls` 为 `[(id, name, arguments_json), ...]`。
    - 非流式：设置 `content` 字符串。
    """

    thinking: list[str] | str | None = None
    text: list[str] | str | None = None
    tool_calls: list[tuple[str, str, str]] = field(default_factory=list)
    finish_reason: str | None = None
    content: str | None = None
    input_tokens: int = 11
    output_tokens: int = 7


def _delta(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_calls: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls,
    )


def _choice_chunk(
    delta: SimpleNamespace | None, finish_reason: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(delta=delta, finish_reason=finish_reason)
        ],
        usage=None,
    )


class _FakeStream:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self._iterator = iter(chunks)

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _stream_chunks(response: FakeResponse) -> list[SimpleNamespace]:
    chunks: list[SimpleNamespace] = []

    for piece in _as_parts(response.thinking):
        chunks.append(_choice_chunk(_delta(reasoning_content=piece)))
    for piece in _as_parts(response.text):
        chunks.append(_choice_chunk(_delta(content=piece)))

    for index, (call_id, name, arguments) in enumerate(response.tool_calls):
        split = len(arguments) // 2
        first, rest = arguments[:split], arguments[split:]
        chunks.append(
            _choice_chunk(
                _delta(
                    tool_calls=[
                        SimpleNamespace(
                            index=index,
                            id=call_id,
                            function=SimpleNamespace(name=name, arguments=first),
                        )
                    ]
                )
            )
        )
        if rest:
            chunks.append(
                _choice_chunk(
                    _delta(
                        tool_calls=[
                            SimpleNamespace(
                                index=index,
                                id=None,
                                function=SimpleNamespace(
                                    name=None, arguments=rest
                                ),
                            )
                        ]
                    )
                )
            )

    finish_reason = response.finish_reason
    if finish_reason is None:
        finish_reason = "tool_calls" if response.tool_calls else "stop"
    # 真实接口的结束 chunk 也带一个空的 delta，finish_reason 在 choice 上。
    chunks.append(_choice_chunk(_delta(), finish_reason=finish_reason))
    # 真实接口在流的最后单独发一个 choices 为空、带 usage 的 chunk。
    chunks.append(
        SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(
                prompt_tokens=response.input_tokens,
                completion_tokens=response.output_tokens,
            ),
        )
    )
    return chunks


class FakeLLMClient:
    """按脚本返回响应的模型客户端；脚本用完后再次调用会报错。"""

    def __init__(self, script: list[FakeResponse]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(copy.deepcopy(kwargs))
        call_number = len(self.calls)
        if call_number > len(self.script):
            raise AssertionError(
                f"FakeLLMClient 第 {call_number} 次调用没有脚本响应"
            )

        response = self.script[call_number - 1]
        if isinstance(response, BaseException):
            raise response
        if kwargs.get("stream"):
            return _FakeStream(_stream_chunks(response))

        content = response.content
        if content is None:
            content = "".join(_as_parts(response.text))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=content))
            ],
            usage=SimpleNamespace(
                prompt_tokens=response.input_tokens,
                completion_tokens=response.output_tokens,
            ),
        )

    def messages(self, call_index: int = -1) -> list[dict[str, Any]]:
        return self.calls[call_index]["messages"]

    def tool_names(self, call_index: int = -1) -> list[str]:
        return [
            tool["function"]["name"]
            for tool in self.calls[call_index].get("tools") or []
        ]


class FakeProvider:
    """按脚本产出模型事件/响应的 Provider；记录收到的每个 `ModelRequest`。

    脚本元素是 `FakeResponse`（流式/非流式按请求方式解读）或异常实例
    （直接抛出，用来测错误路径）。
    """

    name = "fake"

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.requests: list[ModelRequest] = []

    def _next(self) -> Any:
        if not self.script:
            raise AssertionError("FakeProvider 收到了多余的请求")
        return self.script.pop(0)

    async def stream(self, request: ModelRequest) -> Any:
        self.requests.append(copy.deepcopy(request))
        item = self._next()
        if isinstance(item, BaseException):
            raise item

        thinking = _as_parts(item.thinking)
        text = _as_parts(item.text)
        for piece in thinking:
            yield ModelThinkingDelta(text=piece)
        for piece in text:
            yield ModelTextDelta(text=piece)
        if item.tool_calls:
            calls: list[ToolUse] = []
            for index, (call_id, name, arguments_json) in enumerate(item.tool_calls):
                use = ToolUse(id=call_id or f"call_{index}", name=name)
                if not arguments_json.strip():
                    use.input = {}
                else:
                    try:
                        value = json.loads(arguments_json)
                    except json.JSONDecodeError:
                        use.input = None
                        use.input_error = "工具参数不是合法 JSON"
                    else:
                        use.input = value if isinstance(value, dict) else None
                        if use.input is None:
                            use.input_error = "工具参数必须是 JSON 对象"
                calls.append(use)
            yield ToolUseReady(calls=calls)
        yield ModelUsage(
            input_tokens=item.input_tokens, output_tokens=item.output_tokens
        )
        yield ModelStreamEnd(
            finish_reason=item.finish_reason
            or ("tool_calls" if item.tool_calls else "stop")
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(copy.deepcopy(request))
        item = self._next()
        if isinstance(item, BaseException):
            raise item
        content = item.content
        if content is None:
            content = "".join(_as_parts(item.text))
        return ModelResponse(
            text=content,
            tool_uses=[],
            usage=Usage(
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
            ),
            raw=content,
        )

    # ---- 断言辅助 ----

    def tool_names(self, request_index: int = -1) -> list[str]:
        return [schema.name for schema in self.requests[request_index].tools]

    def messages(self, request_index: int = -1):
        return self.requests[request_index].messages


def provider_error(recoverable: bool = True) -> ProviderError:
    return ProviderError("测试用模型调用失败", recoverable=recoverable)


__all__ = [
    "FakeLLMClient",
    "FakeProvider",
    "FakeResponse",
    "provider_error",
]

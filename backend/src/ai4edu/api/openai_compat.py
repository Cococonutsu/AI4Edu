"""OpenAI 兼容厂商的公共转译；厂商差异在各自文件里覆写。

本模块（与 `api/client.py`）是唯一可以 `import openai` 的地方：
内部消息 ⇄ OpenAI 兼容格式（system 固定在首条、图片在文字前、工具调用、
思考只回传本回合）、请求参数组装、流解析（思考在 `delta.reasoning_content`、
工具调用分片按 `index` 拼接、空 choices 的 usage 分片）、异常 →
`ProviderError(recoverable)`。

`GLMProvider` 与 `DeepSeekProvider` 继承 `OpenAICompatProvider`；厂商特有的
协议差异（例如 DeepSeek 思考模式下 `tool_choice` 的限制）只在各自文件里覆写。
收到的 `ModelRequest.messages` 已经过 `prepare_messages()`，此处只做格式转换。

对应 `docs/architecture.md` 第 2.2 节（Provider 协议与厂商实现）。
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from ai4edu.models.contracts import (
    ImageLoader,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
    ModelUsage,
    ProviderError,
    ToolSchema,
    ToolUse,
    ToolUseReady,
    Usage,
)
from ai4edu.models.content import (
    ImageBlock,
    InlineImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    tool_result_text,
)

_RECOVERABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def image_data_url(mime_type: str, data: bytes) -> str:
    """把图片编码成 `image_url` 可用的 data URL。"""

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _to_wire(request: ModelRequest) -> list[dict[str, Any]]:
    """内部消息 → OpenAI 兼容 `messages`；system 非空时固定在第一条。"""

    result: list[dict[str, Any]] = []
    if request.system:
        result.append({"role": "system", "content": request.system})

    for message in request.messages:
        if message.role == "user":
            result.append(_user_message(message, request.image_loader))
        elif message.role == "assistant":
            result.append(
                _assistant_message(
                    message, include_reasoning_for_turn=request.reasoning_turn_id
                )
            )
        else:
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            # 富内容块渲染成文本再发给模型（厂商接口只收字符串）。
                            "content": tool_result_text(block.content),
                        }
                    )

    return result


def _user_message(
    message: Any, image_loader: ImageLoader | None
) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    texts: list[str] = []

    for block in message.content:
        if isinstance(block, InlineImageBlock):
            images.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url(block.mime_type, block.data)
                    },
                }
            )
        elif isinstance(block, ImageBlock):
            if image_loader is None:
                raise ProviderError(
                    f"消息包含附件 {block.attachment_id}，但请求没有提供 image_loader",
                    recoverable=False,
                )
            mime_type, data = image_loader(block.attachment_id)
            images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url(mime_type, data)},
                }
            )
        elif isinstance(block, TextBlock):
            texts.append(block.text)

    text = "".join(texts)
    if not images:
        return {"role": "user", "content": text}

    # 图片放在文字前面，和实测可用的请求格式一致。
    content: list[dict[str, Any]] = list(images)
    if text:
        content.append({"type": "text", "text": text})
    return {"role": "user", "content": content}


def _assistant_message(
    message: Any, *, include_reasoning_for_turn: str | None
) -> dict[str, Any]:
    texts: list[str] = []
    reasoning: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in message.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            arguments = block.input
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": arguments,
                    },
                }
            )
        elif isinstance(block, ThinkingBlock):
            reasoning.append(block.text)

    payload: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(texts),
    }
    if tool_calls:
        payload["tool_calls"] = tool_calls

    turn_id = getattr(message, "turn_id", None)
    if (
        include_reasoning_for_turn is not None
        and turn_id == include_reasoning_for_turn
    ):
        reasoning_text = "".join(reasoning)
        if reasoning_text:
            payload["reasoning_content"] = reasoning_text

    return payload


def _tool_schema_to_wire(schema: ToolSchema) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": schema.input_schema,
        },
    }


def _usage_from_response(usage: Any) -> Usage:
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def _parse_tool_uses(pending: dict[int, dict[str, str]]) -> list[ToolUse]:
    calls: list[ToolUse] = []
    for index, slot in sorted(pending.items()):
        use = ToolUse(
            id=slot["id"] or f"call_{index}",
            name=slot["name"],
        )
        raw = slot["arguments"]
        if not raw.strip():
            use.input = {}
        else:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                use.input = None
                use.input_error = f"工具参数不是合法 JSON：{exc}"
            else:
                if isinstance(value, dict):
                    use.input = value
                else:
                    use.input = None
                    use.input_error = "工具参数必须是 JSON 对象"
        calls.append(use)
    return calls


def _to_provider_error(exc: Exception) -> ProviderError:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return ProviderError(str(exc), recoverable=True)
    if isinstance(exc, APIStatusError):
        recoverable = exc.status_code in _RECOVERABLE_STATUS
        return ProviderError(str(exc), recoverable=recoverable)
    return ProviderError(str(exc), recoverable=False)


class OpenAICompatProvider:
    """OpenAI 兼容接口的公共 Provider；子类给出 `name` 并覆写协议差异。"""

    name: str = ""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    def _params(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model,
            "messages": _to_wire(request),
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.tools:
            params["tools"] = [
                _tool_schema_to_wire(schema) for schema in request.tools
            ]
            params["tool_choice"] = request.tool_choice
        if request.thinking == "off":
            params["extra_body"] = {"thinking": {"type": "disabled"}}
        return params

    async def stream(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelEvent]:
        params = self._params(request, stream=True)
        try:
            stream = await self._client.chat.completions.create(**params)
        except Exception as exc:
            raise _to_provider_error(exc) from exc

        pending: dict[int, dict[str, str]] = {}
        finish_reason = "stop"
        usage = Usage()

        try:
            async for chunk in stream:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = _usage_from_response(chunk_usage)

                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue

                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield ModelThinkingDelta(text=str(reasoning))

                content = getattr(delta, "content", None)
                if content:
                    yield ModelTextDelta(text=str(content))

                for tool_delta in getattr(delta, "tool_calls", None) or []:
                    index = int(getattr(tool_delta, "index", 0) or 0)
                    slot = pending.setdefault(
                        index, {"id": "", "name": "", "arguments": ""}
                    )
                    call_id = getattr(tool_delta, "id", None)
                    if call_id:
                        slot["id"] = str(call_id)
                    function = getattr(tool_delta, "function", None)
                    if function is not None:
                        name = getattr(function, "name", None)
                        if name:
                            slot["name"] = str(name)
                        arguments = getattr(function, "arguments", None)
                        if arguments:
                            slot["arguments"] += str(arguments)

                choice_finish = getattr(choice, "finish_reason", None)
                if choice_finish:
                    finish_reason = str(choice_finish)
        except Exception as exc:
            raise _to_provider_error(exc) from exc

        if pending:
            yield ToolUseReady(calls=_parse_tool_uses(pending))
        yield ModelUsage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        yield ModelStreamEnd(finish_reason=finish_reason)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        params = self._params(request, stream=False)
        try:
            response = await self._client.chat.completions.create(**params)
        except Exception as exc:
            raise _to_provider_error(exc) from exc

        choices = getattr(response, "choices", None) or []
        raw = ""
        wire_tool_calls: list[Any] = []
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                raw = str(getattr(message, "content", None) or "")
                wire_tool_calls = list(getattr(message, "tool_calls", None) or [])

        pending: dict[int, dict[str, str]] = {}
        for index, call in enumerate(wire_tool_calls):
            function = getattr(call, "function", None)
            pending[index] = {
                "id": str(getattr(call, "id", "") or ""),
                "name": str(getattr(function, "name", "") or ""),
                "arguments": str(getattr(function, "arguments", "") or ""),
            }

        return ModelResponse(
            text=raw,
            tool_uses=_parse_tool_uses(pending),
            usage=_usage_from_response(getattr(response, "usage", None)),
            raw=raw,
        )


__all__ = ["OpenAICompatProvider", "image_data_url"]

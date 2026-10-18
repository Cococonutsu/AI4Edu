"""流式与非流式模型调用。

解析智谱 OpenAI 兼容接口的增量格式：思考在 `delta.reasoning_content`，
正文在 `delta.content`，工具调用在 `delta.tool_calls`（按 `index` 拼接）。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ToolCallsReady:
    calls: list[ToolCall]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamEnd:
    finish_reason: str
    usage: Usage = field(default_factory=Usage)


LLMEvent = TextDelta | ThinkingDelta | ToolCallsReady | StreamEnd


@dataclass
class JsonResult:
    data: dict[str, Any]
    raw: str
    usage: Usage


class LLMJsonError(Exception):
    """模型输出中找不到可解析的 JSON 对象。"""

    def __init__(self, raw: str) -> None:
        super().__init__("模型输出不是合法 JSON")
        self.raw = raw


def _usage_from_response(usage: Any) -> Usage:
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


async def stream_chat(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 8192,
) -> AsyncIterator[LLMEvent]:
    """流式调用模型，按到达顺序产出正文/思考增量，结束时给出完整工具调用。"""

    params: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        params["tools"] = tools

    stream = await client.chat.completions.create(**params)

    pending: dict[int, dict[str, str]] = {}
    finish_reason = "stop"
    usage = Usage()

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
            yield ThinkingDelta(text=str(reasoning))

        content = getattr(delta, "content", None)
        if content:
            yield TextDelta(text=str(content))

        for tool_delta in getattr(delta, "tool_calls", None) or []:
            index = int(getattr(tool_delta, "index", 0) or 0)
            slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
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

    if pending:
        calls = [
            ToolCall(
                id=slot["id"] or f"call_{index}",
                name=slot["name"],
                arguments=slot["arguments"],
            )
            for index, slot in sorted(pending.items())
        ]
        yield ToolCallsReady(calls=calls)

    yield StreamEnd(finish_reason=finish_reason, usage=usage)


def _strip_code_fences(text: str) -> str:
    """去掉 Markdown 代码围栏标记，保留其中的 JSON 文本。"""

    return re.sub(r"```[A-Za-z0-9_-]*", "", text).strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从文本里取第一个完整的 `{...}` 并解析；找不到或解析失败返回 None。"""

    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = cleaned.find("{", start + 1)
    return None


async def complete_json(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 8192,
) -> JsonResult:
    """非流式调用并解析 JSON；解析失败抛 `LLMJsonError`。"""

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    choices = getattr(response, "choices", None) or []
    raw = ""
    if choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            raw = str(getattr(message, "content", None) or "")

    data = extract_json_object(raw)
    if data is None:
        raise LLMJsonError(raw)

    return JsonResult(data=data, raw=raw, usage=_usage_from_response(getattr(response, "usage", None)))

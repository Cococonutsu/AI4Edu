"""内部消息 → OpenAI 兼容接口消息格式。

本模块不了解辅导业务，只按内容块类型转换。图片通过 `image_loader` 读取后
编码为 base64 data URL；工具调用转成 `tool_calls`，结果转成 `tool` 角色消息。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterable
from typing import Any

ImageLoader = Callable[[int], tuple[str, bytes]]


def image_data_url(mime_type: str, data: bytes) -> str:
    """把图片编码成 `image_url` 可用的 data URL。"""

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _block_type(block: Any) -> str:
    return str(getattr(block, "type", ""))


def _block_value(block: Any, name: str, default: Any = None) -> Any:
    return getattr(block, name, default)


def _missing_tool_message(tool_call_id: str) -> dict[str, Any]:
    """接口要求每个 tool_call 都有响应；缺失时补一条错误结果。"""

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": "工具未执行",
    }


def _assistant_message(
    message: Any,
    *,
    include_reasoning_for_turn: str | None,
) -> tuple[dict[str, Any], list[str]]:
    texts: list[str] = []
    reasoning: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in getattr(message, "content", []):
        block_type = _block_type(block)
        if block_type == "text":
            texts.append(str(_block_value(block, "text", "")))
        elif block_type == "thinking":
            reasoning.append(str(_block_value(block, "text", "")))
        elif block_type == "tool_use":
            arguments = _block_value(block, "input", {})
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": str(_block_value(block, "id", "")),
                    "type": "function",
                    "function": {
                        "name": str(_block_value(block, "name", "")),
                        "arguments": arguments,
                    },
                }
            )

    payload: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(texts),
    }
    if tool_calls:
        payload["tool_calls"] = tool_calls

    turn_id = getattr(message, "turn_id", None)
    if include_reasoning_for_turn is not None and turn_id == include_reasoning_for_turn:
        reasoning_text = "".join(reasoning)
        if reasoning_text:
            payload["reasoning_content"] = reasoning_text

    return payload, [call["id"] for call in tool_calls]


def _user_message(message: Any, image_loader: ImageLoader) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    texts: list[str] = []

    for block in getattr(message, "content", []):
        block_type = _block_type(block)
        if block_type == "image":
            attachment_id = int(_block_value(block, "attachment_id"))
            mime_type, data = image_loader(attachment_id)
            images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url(mime_type, data)},
                }
            )
        elif block_type == "text":
            texts.append(str(_block_value(block, "text", "")))

    text = "".join(texts)
    if not images:
        return {"role": "user", "content": text}

    # 图片放在文字前面，和实测可用的请求格式一致。
    content: list[dict[str, Any]] = list(images)
    if text:
        content.append({"type": "text", "text": text})
    return {"role": "user", "content": content}


def _tool_messages(message: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in getattr(message, "content", []):
        if _block_type(block) != "tool_result":
            continue
        result.append(
            {
                "role": "tool",
                "tool_call_id": str(_block_value(block, "tool_use_id", "")),
                "content": str(_block_value(block, "content", "")),
            }
        )
    return result


def to_openai_messages(
    messages: Iterable[Any],
    *,
    image_loader: ImageLoader,
    include_reasoning_for_turn: str | None,
) -> list[dict[str, Any]]:
    """把 agent 消息对象转换成 OpenAI 兼容接口的 `messages`。

    - `user`：图片转 data URL（放在文字前）。
    - `assistant`：文字拼成 `content`，工具调用转 `tool_calls`；思考内容只在
      本回合（`turn_id == include_reasoning_for_turn`）回传。
    - `tool`：转成 `role=tool` 消息。

    如果某个 assistant 消息的 tool_call 没有对应结果，会补一条“工具未执行”，
    避免接口因消息不完整而报错。
    """

    result: list[dict[str, Any]] = []
    pending_tool_ids: list[str] = []

    def flush_missing() -> None:
        for tool_call_id in pending_tool_ids:
            result.append(_missing_tool_message(tool_call_id))
        pending_tool_ids.clear()

    for message in messages:
        role = str(getattr(message, "role", ""))

        if role == "tool":
            for tool_message in _tool_messages(message):
                result.append(tool_message)
                tool_call_id = tool_message["tool_call_id"]
                if tool_call_id in pending_tool_ids:
                    pending_tool_ids.remove(tool_call_id)
            continue

        # 工具结果必须紧跟在 assistant 之后；进入下一条非 tool 消息前补齐。
        flush_missing()

        if role == "assistant":
            assistant_message, call_ids = _assistant_message(
                message,
                include_reasoning_for_turn=include_reasoning_for_turn,
            )
            result.append(assistant_message)
            pending_tool_ids.extend(call_ids)
        elif role == "user":
            result.append(_user_message(message, image_loader))
        else:
            # 未知角色按文本处理，避免静默丢消息。
            texts = [
                str(_block_value(block, "text", ""))
                for block in getattr(message, "content", [])
                if _block_type(block) == "text"
            ]
            result.append({"role": "user", "content": "".join(texts)})

    flush_missing()
    return result

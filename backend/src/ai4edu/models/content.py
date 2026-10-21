"""消息内容块。

JSON 格式严格按 `docs/architecture.md` 7.1 节；未知块类型读取时忽略，
避免旧数据导致整条会话无法加载。`InlineImageBlock` 只用于构造模型请求，
不入库。

本包不导入 `ai4edu` 的其他子包。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias


@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImageBlock:
    attachment_id: int
    type: Literal["image"] = "image"


@dataclass
class InlineImageBlock:
    """带原始字节的图片块，只出现在发给模型的请求里，不写入数据库。"""

    mime_type: str
    data: bytes
    type: Literal["inline_image"] = "inline_image"


@dataclass
class ThinkingBlock:
    text: str
    type: Literal["thinking"] = "thinking"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    type: Literal["tool_use"] = "tool_use"


# 工具结果的内容：目前是纯文本；预留更细粒度的富内容块（结构化命中、
# 图片等，对齐 cc 的 ToolResult.content 联合类型）。入库按原样写入
# content_json（两种形态都是合法 JSON），发给模型前用 `tool_result_text`
# 渲染成文本。
ToolResultContent: TypeAlias = str | list[dict[str, Any]]


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: ToolResultContent
    is_error: bool = False
    status_label: str = ""
    # 允许下发给浏览器的展示数据（`draw_figure` 的图）；旧数据没有这个字段。
    display: dict[str, Any] | None = None
    type: Literal["tool_result"] = "tool_result"


def tool_result_text(content: ToolResultContent) -> str:
    """把工具结果内容渲染成给模型的纯文本：字符串原样；富内容块逐块取
    `text` 字段（没有的渲染成 JSON），用换行连接。"""

    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            parts.append(
                str(text) if text is not None else json.dumps(item, ensure_ascii=False)
            )
        else:
            parts.append(str(item))
    return "\n".join(parts)


Block: TypeAlias = (
    TextBlock
    | ImageBlock
    | InlineImageBlock
    | ThinkingBlock
    | ToolUseBlock
    | ToolResultBlock
)


def block_to_json(block: Block) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ImageBlock):
        return {"type": "image", "attachment_id": block.attachment_id}
    if isinstance(block, InlineImageBlock):
        raise TypeError("InlineImageBlock 仅用于模型请求，不能写入数据库")
    if isinstance(block, ThinkingBlock):
        return {"type": "thinking", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    if isinstance(block, ToolResultBlock):
        data: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
            "status_label": block.status_label,
        }
        if block.display is not None:
            data["display"] = block.display
        return data
    raise TypeError(f"未知内容块：{type(block)!r}")


def blocks_to_json(blocks: list[Block]) -> list[dict[str, Any]]:
    return [block_to_json(block) for block in blocks]


def block_from_json(data: Any) -> Block | None:
    if not isinstance(data, dict):
        return None

    block_type = data.get("type")
    if block_type == "text":
        return TextBlock(text=str(data.get("text") or ""))
    if block_type == "image":
        raw_id = data.get("attachment_id")
        if raw_id is None:
            return None
        return ImageBlock(attachment_id=int(raw_id))
    if block_type == "thinking":
        return ThinkingBlock(text=str(data.get("text") or ""))
    if block_type == "tool_use":
        raw_input = data.get("input")
        return ToolUseBlock(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            input=raw_input if isinstance(raw_input, dict) else {},
        )
    if block_type == "tool_result":
        raw_content = data.get("content")
        # 新数据可能是富内容块列表，旧数据一律是字符串。
        content: ToolResultContent = (
            raw_content
            if isinstance(raw_content, (str, list))
            else str(raw_content or "")
        )
        raw_display = data.get("display")
        return ToolResultBlock(
            tool_use_id=str(data.get("tool_use_id") or ""),
            content=content,
            is_error=bool(data.get("is_error")),
            status_label=str(data.get("status_label") or ""),
            display=raw_display if isinstance(raw_display, dict) else None,
        )
    return None


def blocks_from_json(data: Any) -> list[Block]:
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    blocks: list[Block] = []
    for item in data:
        block = block_from_json(item)
        if block is not None:
            blocks.append(block)
    return blocks

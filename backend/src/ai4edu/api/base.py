"""Provider 协议与模型请求/响应的内部结构（`docs/architecture.md` 2.2 节）。

厂商实现负责：内部消息 → 厂商请求；厂商流 → `ModelEvent`；厂商异常 →
`ProviderError(recoverable)`。厂商特有的东西只出现在该厂商文件里。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

from ai4edu.models.contracts import ProviderError, ThinkingMode, ToolChoice, ToolSchema
from ai4edu.models.messages import Message

__all__ = [
    "ImageLoader",
    "ModelEvent",
    "ModelRequest",
    "ModelResponse",
    "ModelStreamEnd",
    "ModelTextDelta",
    "ModelThinkingDelta",
    "ModelUsage",
    "Provider",
    "ProviderError",
    "ThinkingMode",
    "ToolChoice",
    "ToolSchema",
    "ToolUse",
    "ToolUseReady",
    "Usage",
]

# 给定附件 id，返回 (mime_type, 原始字节)；由 query_engine 构造并注入请求。
ImageLoader = Callable[[int], tuple[str, bytes]]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ModelRequest:
    model: str
    system: str
    messages: list[Message]  # 内部消息，已规范化
    tools: Sequence[ToolSchema] = ()
    max_tokens: int = 8192
    thinking: ThinkingMode = "on"
    tool_choice: ToolChoice = "auto"
    # 思考内容只回传本回合的消息（turn_id 相同）。
    reasoning_turn_id: str | None = None
    image_loader: ImageLoader | None = None


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any] | None = None
    # 参数不是合法 JSON 时记录原因，由循环回给模型重试，不抛异常。
    input_error: str | None = None


# ---- 模型层事件（Provider 从厂商流解析产出；core/events 转发） ----


@dataclass
class ModelTextDelta:
    text: str


@dataclass
class ModelThinkingDelta:
    text: str


@dataclass
class ToolUseReady:
    calls: list[ToolUse]


@dataclass
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ModelStreamEnd:
    finish_reason: str


ModelEvent: TypeAlias = (
    ModelTextDelta
    | ModelThinkingDelta
    | ToolUseReady
    | ModelUsage
    | ModelStreamEnd
)


@dataclass
class ModelResponse:
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    raw: str = ""


@runtime_checkable
class Provider(Protocol):
    name: str

    def stream(self, request: ModelRequest) -> Any: ...

    def complete(self, request: ModelRequest) -> Any: ...


__all__ = [
    "ImageLoader",
    "ModelEvent",
    "ModelRequest",
    "ModelResponse",
    "ModelStreamEnd",
    "ModelTextDelta",
    "ModelThinkingDelta",
    "ModelUsage",
    "Provider",
    "ProviderError",
    "ThinkingMode",
    "ToolChoice",
    "ToolSchema",
    "ToolUse",
    "ToolUseReady",
    "Usage",
]

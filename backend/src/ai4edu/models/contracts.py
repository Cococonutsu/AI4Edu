"""模型调用的全部契约：类型、事件与 Provider 协议（`docs/architecture.md` 2.2 节）。

`api/` 的厂商实现（glm、deepseek、openai_compat）把内部消息转成厂商请求、
把厂商流解析成 `ModelEvent`、把厂商异常映射成 `ProviderError(recoverable)`；
`core/query_loop.py` 只依赖 `models/` 与传入的参数；`tools/`、`hooks/` 只通过
这里的类型引用模型能力，不导入 `ai4edu.api`。纯标准库，不导入其他子包
（`Message` 来自本包的 messages.py）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

from ai4edu.models.messages import Message

ThinkingMode = Literal["on", "off"]
ToolChoice = Literal["auto", "required", "none"]


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]


# 给定附件 id，返回 (mime_type, 原始字节)；由 query_engine 构造并注入请求。
ImageLoader = Callable[[int], tuple[str, bytes]]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    # 提示词缓存命中的 token 数（厂商 usage 里的 cached_tokens /
    # prompt_cache_hit_tokens；没有缓存或厂商不报告时为 0）。
    cached_tokens: int = 0


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


# ---- 模型层事件（Provider 从厂商流解析产出，只在本回合内消费） ----


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
    cached_tokens: int = 0


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

    def stream(self, request: ModelRequest) -> Any: ...  # AsyncIterator[ModelEvent]

    def complete(self, request: ModelRequest) -> Any: ...  # ModelResponse


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
    "ThinkingMode",
    "ToolChoice",
    "ToolSchema",
    "ToolUse",
    "ToolUseReady",
    "Usage",
]

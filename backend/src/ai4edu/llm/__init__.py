"""模型调用层：OpenAI 兼容客户端、消息格式化、流式与非流式调用。"""

from ai4edu.llm.client import make_client
from ai4edu.llm.stream import (
    JsonResult,
    LLMJsonError,
    StreamEnd,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolCallsReady,
    Usage,
    complete_json,
    stream_chat,
)

__all__ = [
    "JsonResult",
    "LLMJsonError",
    "StreamEnd",
    "TextDelta",
    "ThinkingDelta",
    "ToolCall",
    "ToolCallsReady",
    "Usage",
    "complete_json",
    "make_client",
    "stream_chat",
]

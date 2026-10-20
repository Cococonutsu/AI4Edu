"""模型调用层：Provider 协议、智谱实现、按配置的工厂、JSON 提取。

只有本包可以导入厂商 SDK（`openai`）；不了解辅导业务。
"""

from ai4edu.api.base import (
    ImageLoader,
    ModelRequest,
    ModelResponse,
    Provider,
    ProviderError,
    ThinkingMode,
    ToolChoice,
    ToolSchema,
    ToolUse,
    Usage,
)
from ai4edu.api.client import make_client, make_provider
from ai4edu.api.json_util import JsonParseError, complete_json, extract_json_object

__all__ = [
    "ImageLoader",
    "JsonParseError",
    "ModelRequest",
    "ModelResponse",
    "Provider",
    "ProviderError",
    "ThinkingMode",
    "ToolChoice",
    "ToolSchema",
    "ToolUse",
    "Usage",
    "complete_json",
    "extract_json_object",
    "make_client",
    "make_provider",
]

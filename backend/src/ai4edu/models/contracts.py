"""模型请求相关的厂商无关契约类型。

`ThinkingMode`、`ToolChoice`、`ToolSchema`、`ProviderError` 同时被
`api/base.py`（Provider 协议）与 `core/query_loop.py`（只依赖 `models/`
与传入的参数）使用，因此放在本包。纯标准库，不导入其他子包。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ThinkingMode = Literal["on", "off"]
ToolChoice = Literal["auto", "required", "none"]


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]


class ProviderError(Exception):
    """模型调用失败。`recoverable=True` 表示可以原步重试。"""

    def __init__(self, message: str, *, recoverable: bool) -> None:
        super().__init__(message)
        self.recoverable = recoverable


__all__ = ["ProviderError", "ThinkingMode", "ToolChoice", "ToolSchema"]

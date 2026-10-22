"""应用异常树：全部应用内异常集中定义（对齐 cc 的 `utils/errors.py`）。

摆放对齐 cc：基类与各领域异常**集中在这一处**定义，业务模块只导入、
不再各自定义异常类。上层可以用一个 `except AI4EduError` 统一兜底，
而不会误捕系统级异常（MemoryError、SystemExit 等）。本模块零依赖，
对应 `docs/architecture.md` 第 2 节（分层）。
"""

from __future__ import annotations

from typing import Literal


class AI4EduError(Exception):
    """所有应用内异常的基类。"""


class ConfigError(AI4EduError):
    """配置错误：框架 YAML / 提醒配置缺失或不合格。"""


class ProviderError(AI4EduError):
    """模型调用失败。`recoverable=True` 表示可以原步重试。"""

    def __init__(self, message: str, *, recoverable: bool) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class MessageSequenceError(AI4EduError):
    """消息序列不符合接口要求，且无法在规范化阶段修复。"""


LoopFailureReason = Literal[
    "provider_error",  # 不可恢复的模型调用失败
    "network_error",  # 可恢复错误重试耗尽（或正文已下发无法重试）
    "max_steps",  # 达到步数上限
    "guard",  # 回合守卫放弃（error_text 为学生可见文字）
]


class LoopFailure(AI4EduError):
    """循环无法继续。reason 由引擎映射成学生可见的错误提示。"""

    def __init__(
        self, reason: LoopFailureReason, message: str | None = None
    ) -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message


class QueryEngineError(AI4EduError):
    """请求不合法（会话或附件不属于当前学生等）。"""


class WebToolsError(AI4EduError):
    """联网工具调用失败。

    `recoverable` 表示同类请求稍后重试是否可能成功（限流、超时、服务端
    5xx 为真；余额不足、参数错误等为假）。工具层不自动重试，把原因原样
    回给模型。
    """

    def __init__(self, message: str, *, recoverable: bool) -> None:
        super().__init__(message)
        self.recoverable = recoverable


__all__ = [
    "AI4EduError",
    "ConfigError",
    "LoopFailure",
    "LoopFailureReason",
    "MessageSequenceError",
    "ProviderError",
    "QueryEngineError",
    "WebToolsError",
]

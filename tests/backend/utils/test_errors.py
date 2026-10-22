"""应用异常都继承公共基类 AI4EduError（对齐 cc 的错误层次）。"""

from __future__ import annotations

from ai4edu.utils.errors import (
    AI4EduError,
    ConfigError,
    LoopFailure,
    MessageSequenceError,
    ProviderError,
    QueryEngineError,
    WebToolsError,
)

_SUBCLASSES = (
    ProviderError,
    MessageSequenceError,
    ConfigError,
    LoopFailure,
    QueryEngineError,
    WebToolsError,
)


def test_all_app_exceptions_share_the_base():
    instances = (
        ProviderError("测试", recoverable=True),
        MessageSequenceError("测试"),
        ConfigError("测试"),
        LoopFailure("max_steps"),
        QueryEngineError("测试"),
        WebToolsError("测试", recoverable=False),
    )
    for cls, instance in zip(_SUBCLASSES, instances):
        assert issubclass(cls, AI4EduError), cls
        assert isinstance(instance, AI4EduError)


def test_base_is_not_system_exception():
    assert not issubclass(AI4EduError, (KeyboardInterrupt, SystemExit))

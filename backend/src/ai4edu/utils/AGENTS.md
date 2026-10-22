# utils/

零依赖的公共定义：项目内最底层，**不导入 `ai4edu` 的任何其他子包**（对齐
cc 的 `utils/`）。任何包都可以安全导入本包；`models/` 的纯度检查也把它
视作等同标准库的例外。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出（`AI4EduError`） |
| `errors.py` | 应用异常树（对齐 cc 的 `utils/errors.py`，集中定义）：`AI4EduError` 基类与 `ConfigError`、`ProviderError(recoverable)`、`MessageSequenceError`、`LoopFailure/LoopFailureReason`、`QueryEngineError`、`WebToolsError(recoverable)`——业务模块只导入使用，不再各自定义异常类 |

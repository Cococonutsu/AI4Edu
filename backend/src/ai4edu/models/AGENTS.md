# models/

内部数据结构与模型调用契约。**不导入 `ai4edu` 的其他子包**（AST 测试强制）。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出 |
| `content.py` | 内容块：`TextBlock`、`ImageBlock`（附件 id）、`InlineImageBlock`（只用于请求，不入库）、`ThinkingBlock`、`ToolUseBlock`、`ToolResultBlock`（`content` 是 `ToolResultContent`：纯文本或富内容块列表，预留细粒度工具结果）；`tool_result_text()` 把富内容渲染成发给模型的文本；JSON 互转 |
| `messages.py` | `Message`；与数据库 `content_json` 互转；序列规范化与校验（`normalize_messages`/`validate_messages`/`prepare_messages`、`MessageSequenceError`），规则见 `docs/architecture.md` 3.1，system 不在消息列表中 |
| `contracts.py` | 模型调用的全部契约：`ThinkingMode`/`ToolChoice`/`ToolSchema`/`ProviderError`、`ModelRequest`/`ModelResponse`、模型层事件家族（`ModelEvent` 等）、`ToolUse`/`Usage`/`ImageLoader`、`Provider` 协议。api/ 实现、core/tools/hooks 消费，使除 `core/query_engine.py` 外无人需要导入 `ai4edu.api` |

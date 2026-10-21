# session/

会话持久化编排。**只有本包（以及 `auth/`、`server/routes/` 的简单增删
改查和 `cli/`）可以调用 `storage/repos`**；`core/`、`hooks/`、`tools/`
通过 `TurnStore` 读写。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出 |
| `store.py` | `TurnStore`：绑定 (db 会话, user_id, conversation_id) 的高层接口——会话、消息（自动分配 seq）、辅导状态、题目、附件、证据、模型调用日志；所有读取按 `user_id` 过滤 |
| `recovery.py` | `repair_history`：加载历史时为被中断回合的孤儿工具调用在内存里补占位结果（数据库原文不动）；与 `prepare_messages` 的修复幂等 |

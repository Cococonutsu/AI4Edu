# src/api/

与后端通信的边界。所有请求使用 `credentials: "same-origin"`，接口类型与 `docs/architecture.md` 第 8 节一致。

| 文件 | 内容 |
|---|---|
| `types.ts` | 用户、会话、消息、附件、NDJSON 事件的 TypeScript 类型 |
| `client.ts` | fetch 封装、`ApiError`、401 通知、响应归一化 |
| `stream.ts` | NDJSON 增量解码器，处理跨块中文、半行、空行与坏行 |

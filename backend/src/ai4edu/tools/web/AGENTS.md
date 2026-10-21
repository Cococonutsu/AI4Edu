# tools/web/

联网工具一家：两个模型可调用的工具 + 它们共用的执行客户端。工具经 `ToolContext.web`（`client.py` 的 `WebTools` 协议）执行，工具层只做参数校验与结果排版；结果只给模型（`display=None`），学生看不到。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包标记 |
| `search.py` | `web_search`：联网搜索（关键词 1–128 字符、条数 1–10 钳制），结果（标题/链接/日期/摘要/相关度/权威度）排版给模型并拼 `after_web_search` 提醒；空结果非错误；未配置或失败返回 `is_error` |
| `fetch.py` | `web_fetch`：读取网页正文（http/https、≤8192 字符、不得带用户名密码），正文截断到 20000 字符后给模型并拼 `after_web_fetch` 提醒；未配置或失败返回 `is_error` |
| `client.py` | 契约与默认实现：`WebTools` 协议、`WebSearchHit`/`WebFetchPage`/`WebToolsError(recoverable)`；`DeepSeekWebTools`（`/v1/tools/search` 与 `/v1/tools/fetch` 的 httpx 客户端：拼端点、Bearer 鉴权、响应映射、超时/HTTP 错误分类，不自动重试）；`make_web_tools(settings)` 无 `DEEPSEEK_API_KEY` 时返回 None。项目里唯一发起厂商 HTTP 的非 api 文件 |

# api/

模型调用层（厂商适配）：`client.py` 按配置创建 Provider（glm/deepseek）并解析
地址与 key；`openai_compat.py` 是 OpenAI 兼容的公共转译基类；`glm.py`、
`deepseek.py` 是各厂商实现（厂商差异以覆写留在各自文件）。不了解辅导业务。

**只有本目录可以 `import openai`，且仅限 `glm.py`、`deepseek.py`、
`openai_compat.py`、`client.py`**；联网工具的厂商 HTTP（`httpx`）在
`tools/web/client.py`，不在本目录。src 中只有 `core/query_engine.py`
可以导入本包（AST 测试强制）；请求/响应、事件与 Provider 协议的契约类型在
`ai4edu.models.contracts`。收到的 `ModelRequest.messages` 已经过
`models.messages.prepare_messages()` 规范化，本层只做格式转换，不重复实现
序列规则。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出（仅 `make_client`/`make_provider`） |
| `client.py` | `make_client`/`make_provider`/`llm_credentials`：按 `settings.llm_provider` 选择厂商（glm/deepseek），未知值报错；地址与 key 的默认解析（`LLM_BASE_URL` 留空按厂商取默认，deepseek 且 `LLM_API_KEY` 留空时用 `DEEPSEEK_API_KEY`） |
| `openai_compat.py` | `OpenAICompatProvider`：内部消息 ⇄ OpenAI 兼容格式（图片 base64 在文字前、工具调用、思考只回传本回合、空 system 不发 system 消息）；流解析（`reasoning_content`、按 `index` 拼接的工具参数、空 choices 的 usage 分片）；`thinking="off"` 时 `extra_body={"thinking":{"type":"disabled"}}`；openai 异常 → `ProviderError(recoverable)` |
| `glm.py` | `GLMProvider`（name="glm"）：继承公共转译；智谱特有事实见模块 docstring |
| `deepseek.py` | `DeepSeekProvider`（name="deepseek"）：继承公共转译；覆写参数组装——思考模式下 `tool_choice=required` 防护性降级为 `auto`（DeepSeek 思考模式仅支持 auto/none）。模型 `deepseek-flash`/`deepseek-v4-pro` |

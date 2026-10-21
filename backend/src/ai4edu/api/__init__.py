"""模型调用层：按配置创建 Provider（厂商实现见 glm.py、deepseek.py）。

只有本包可以导入厂商 SDK（`openai`）；不了解辅导业务。联网工具的厂商
HTTP（httpx）在 `tools/web_client.py`。请求/响应、事件与 Provider 协议的
契约类型在 `ai4edu.models.contracts`。
"""

from ai4edu.api.client import make_client, make_provider

__all__ = ["make_client", "make_provider"]

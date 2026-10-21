"""DeepSeek Provider：OpenAI 兼容接口。

厂商特有事实（2026-10 官方文档）：

- base_url 为 ``https://api.deepseek.com``（OpenAI 兼容）；聊天模型名
  ``deepseek-flash``、``deepseek-v4-pro``。
- 思考开关是请求参数 ``thinking: {"type": "enabled"|"disabled"}``，默认
  ``enabled``；用 openai SDK 时放进 ``extra_body``，与 GLM 同形。
- 流式思考字段是 ``delta.reasoning_content``，与 GLM 同名；``tool_calls``
  流式分片与 ``usage`` 结构同 OpenAI。
- ``tools`` 仅支持 function 类型；**思考模式下 ``tool_choice`` 只允许
  ``auto``/``none``，``required`` 或指定函数会返回 400**。本系统目前只发
  ``auto``，下面的覆写是防御性转译。
- 错误响应 OpenAI 兼容，openai SDK 的异常类可直接使用（公共映射见
  ``api/openai_compat.py``）。

公共转译继承自 `OpenAICompatProvider`；DeepSeek 自己的协议差异只在本文件
覆写，后续协议变化也只改这里。

对应 `docs/architecture.md` 第 2.2 节（Provider 协议与厂商实现）。
"""

from __future__ import annotations

from typing import Any

from ai4edu.models.contracts import ModelRequest
from ai4edu.api.openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"

    def _params(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        """在公共参数上做 DeepSeek 防护：思考模式不接受 ``required``。"""

        params = super()._params(request, stream=stream)
        if request.thinking == "on" and params.get("tool_choice") == "required":
            params["tool_choice"] = "auto"
        return params


__all__ = ["DeepSeekProvider"]

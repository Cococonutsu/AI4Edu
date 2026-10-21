"""智谱 GLM Provider：OpenAI 兼容接口。

GLM 特有事实：思考开关 `thinking` 放在 `extra_body`（`thinking="off"` 时发
`{"thinking": {"type": "disabled"}}`，默认开启）；思考内容在
`delta.reasoning_content`。内部消息转译、请求参数组装、流解析与异常映射等
公共逻辑已上移到 `api/openai_compat.py`，本文件只保留厂商身份。
"""

from __future__ import annotations

from ai4edu.api.openai_compat import OpenAICompatProvider, image_data_url


class GLMProvider(OpenAICompatProvider):
    name = "glm"


__all__ = ["GLMProvider", "image_data_url"]

"""从模型输出中提取 JSON：与厂商无关，供工具使用。"""

from __future__ import annotations

import json
import re
from typing import Any

from ai4edu.api.base import ModelRequest, ModelResponse, Provider


class JsonParseError(Exception):
    """模型输出中找不到可解析的 JSON 对象。"""

    def __init__(self, raw: str) -> None:
        super().__init__("模型输出不是合法 JSON")
        self.raw = raw


def _strip_code_fences(text: str) -> str:
    """去掉 Markdown 代码围栏标记，保留其中的 JSON 文本。"""

    return re.sub(r"```[A-Za-z0-9_-]*", "", text).strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从文本里取第一个完整的 `{...}` 并解析；找不到或解析失败返回 None。"""

    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = cleaned.find("{", start + 1)
    return None


async def complete_json(
    provider: Provider, request: ModelRequest
) -> tuple[dict[str, Any], ModelResponse]:
    """调用 `provider.complete` 并从输出提取 JSON；失败抛 `JsonParseError`。"""

    response = await provider.complete(request)
    data = extract_json_object(response.text)
    if data is None:
        raise JsonParseError(response.raw)
    return data, response


__all__ = ["JsonParseError", "complete_json", "extract_json_object"]

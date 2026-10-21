"""回合内发给模型的短文字与学生可见错误提示。

文字在 `config/prompts/reminders.yaml`（带版本号），由 `load_reminders`
读取；占位符格式 `{name}`（Python str.format），模板里出现而调用没给的
占位符会抛 `ConfigError`，而不是留空。

对应 `docs/architecture.md` 第 2.1 节（提示词唯一出口）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ai4edu.tutoring.framework import ConfigError

_REQUIRED_KEYS = (
    "already_sent",
    "guard_empty",
    "after_analyze_confident",
    "after_web_fetch",
    "after_web_search",
    "figure_invalid",
    "figure_shown",
    "web_fetch_failed",
    "web_search_failed",
    "web_tools_unavailable",
    "analyze_failed",
    "unknown_tool",
    "bad_tool_arguments",
    "tool_execution_failed",
    "student_guard_error",
    "student_max_steps",
    "student_generic_error",
    "student_empty_reply",
    "student_network_error",
)

_PROMPT_VERSION_RE = re.compile(r"prompt_version\s*:\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_LEADING_HASH_COMMENT_RE = re.compile(r"(?:^\s*#[^\n]*\n)+", re.MULTILINE)


class Reminders:
    """提醒文字的只读视图。"""

    def __init__(self, texts: dict[str, str]) -> None:
        missing = [key for key in _REQUIRED_KEYS if key not in texts]
        if missing:
            raise ConfigError(
                "reminders.yaml 缺少键：" + "、".join(missing)
            )
        self._texts = dict(texts)

    def text(self, key: str, /, **format_values: Any) -> str:
        template = self._texts.get(key)
        if template is None:
            raise ConfigError(f"reminders.yaml 中没有键 {key!r}")
        try:
            # 始终执行 format：模板里的 {name} 没有对应取值时会抛 KeyError。
            return template.format(**format_values)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(
                f"reminders.yaml 的 {key!r} 与占位参数不匹配：{exc}"
            ) from exc

    @property
    def student_guard_error(self) -> str:
        return self._texts["student_guard_error"]

    @property
    def student_max_steps(self) -> str:
        return self._texts["student_max_steps"]

    @property
    def student_generic_error(self) -> str:
        return self._texts["student_generic_error"]

    @property
    def student_empty_reply(self) -> str:
        return self._texts["student_empty_reply"]

    @property
    def student_network_error(self) -> str:
        return self._texts["student_network_error"]


def load_reminders(config_dir: Path) -> Reminders:
    """读取 `config_dir/prompts/reminders.yaml` 并解析版本号。"""

    path = Path(config_dir) / "prompts" / "reminders.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取提醒配置 {path}：{exc}") from exc
    if not text.strip():
        raise ConfigError("reminders.yaml 为空")

    first_line = text.splitlines()[0]
    if _PROMPT_VERSION_RE.search(first_line) is None:
        raise ConfigError(
            "reminders.yaml 首行注释缺少 prompt_version，应形如 "
            "`# prompt_version: xxx`"
        )

    body = _LEADING_HASH_COMMENT_RE.sub("", text, count=1)
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise ConfigError(f"reminders.yaml 不是合法的 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("reminders.yaml 的顶层必须是映射（key: value）")
    return Reminders({str(key): str(value) for key, value in data.items()})


__all__ = ["Reminders", "load_reminders"]

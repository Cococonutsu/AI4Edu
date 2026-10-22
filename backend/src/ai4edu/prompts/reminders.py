"""回合内发给模型的短文字与学生可见错误提示（对应 `docs/architecture.md` 2.1 节）。

文字以 Python 常量集中在本模块（对齐 cc 的 sections.py 管理方式）：
占位符格式 `{name}`（str.format），调用缺参时报错而不是留空；改动任何文字
时提升 `REMINDERS_VERSION`。分两组：给模型的（临时提醒、工具结果中的
指令）与学生可见的错误提示（前端直接显示）。
"""

from __future__ import annotations

from typing import Any

from ai4edu.utils.errors import ConfigError

# 版本号随文字内容变化提升；文字搬进代码不改变内容，版本不变。
REMINDERS_VERSION = "reminders-2026.10.21-3"

# ---- 给模型的短文字 ----

_MODEL_TEXTS: dict[str, str] = {
    # 回合守卫：这一步既没有正文也没有工具调用（例如只有思考就结束了）
    "guard_empty": (
        "（系统提醒：你这一步没有对学生说任何话。请立刻回复学生："
        "能直接回答的就直接写正文；需要记诊断或拆题的就调用对应工具。）"
    ),
    # 本步已有正文下发给学生，下一步不许重写
    "already_sent": (
        "（系统提醒：你在本回合已经对学生说过上面那段话，学生已经看到。"
        "不要重复或改写它；如果没有新的内容要补充，就不要再输出正文。）"
    ),
    # analyze_problem 工具结果里给辅导老师的下一步指令
    "after_analyze_confident": (
        "用一句话复述题目要求，然后围绕当前子任务提出第一个问题；"
        "直接写正文，不要调用工具。"
    ),
    "analyze_failed": (
        "题目模型不合格：{error}。请修正后重新调用 analyze_problem；"
        "如果题目文字或图片确实看不清，请让学生补发更清晰的内容。"
    ),
    # draw_figure 工具结果
    "figure_invalid": "图形描述不合格：{error}。请修正后重新调用 draw_figure。",
    "figure_shown": (
        "图已打开，学生能看到并拖动。请只用一两句话说明该看什么、"
        "该拖哪个点或滑块，不要复述图中的数值，然后继续围绕当前子任务提问。"
    ),
    # 联网工具（web_search / web_fetch）的工具结果
    "after_web_search": (
        "搜索结果已经给你。只取教学需要的事实，用学生年级能听懂的话概括，"
        "不贴链接和原文，然后接回当前子任务。"
    ),
    "after_web_fetch": (
        "网页内容已经给你。只取与当前教学相关的部分用学生能懂的话概括，"
        "不要照搬原文，然后接回当前子任务。"
    ),
    "web_search_failed": (
        "联网搜索没有成功（{error}）。不要编造网上的信息："
        "简单告诉学生这次没查到，再基于课本知识继续辅导。"
    ),
    "web_fetch_failed": (
        "网页抓取没有成功（{error}）。可以换更具体的关键词重新 web_search，"
        "或基于已有信息继续辅导。"
    ),
    "web_tools_unavailable": (
        "联网功能当前没有开通。简单告诉学生暂时查不了网，"
        "然后基于课本知识继续辅导。"
    ),
    # 正文被输出长度截断（finish_reason=length）后的续写提醒
    "truncated_continuation": (
        "（系统提醒：你上一段回复因为长度限制被截断了。"
        "请从中断的地方继续写完，不要重复已经说过的内容。）"
    ),
    # 工具执行层回给模型的错误说明
    "unknown_tool": "未知工具 {name}，请只使用提供的工具。",
    "bad_tool_arguments": "{error}。请重新调用 {name} 并给出合法 JSON 参数。",
    "tool_execution_failed": "工具 {name} 执行失败，请换一种方式继续。",
}

# ---- 学生可见的错误提示（前端直接显示） ----

_STUDENT_TEXTS: dict[str, str] = {
    "student_guard_error": "老师刚才走神了，请再发一次你的回答。",
    "student_max_steps": "老师需要再想一想，请稍后再试。",
    "student_generic_error": "出了点问题，请稍后再试。",
    "student_empty_reply": (
        "这次没能读懂题目，可以换一张更清晰的照片，或者把题目打字发给我。"
    ),
    "student_network_error": "老师这边网络不太好，请稍后再发一次。",
}

_TEXTS: dict[str, str] = {**_MODEL_TEXTS, **_STUDENT_TEXTS}

_STUDENT_KEYS = (
    "student_guard_error",
    "student_max_steps",
    "student_generic_error",
    "student_empty_reply",
    "student_network_error",
)


class Reminders:
    """提醒文字的只读视图。"""

    def __init__(self) -> None:
        missing = [key for key in _STUDENT_KEYS if key not in _TEXTS]
        if missing:
            raise ConfigError("reminders 常量缺少键：" + "、".join(missing))
        self._texts = dict(_TEXTS)

    def text(self, key: str, /, **format_values: Any) -> str:
        template = self._texts.get(key)
        if template is None:
            raise ConfigError(f"reminders 中没有键 {key!r}")
        try:
            # 始终执行 format：模板里的 {name} 没有对应取值时会抛 KeyError。
            return template.format(**format_values)
        except (KeyError, IndexError, ValueError) as exc:
            raise ConfigError(
                f"reminders 的 {key!r} 与占位参数不匹配：{exc}"
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


__all__ = ["REMINDERS_VERSION", "Reminders"]

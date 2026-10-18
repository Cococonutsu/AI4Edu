"""组装辅导系统提示词与工具提示词。

状态区块每一步动态生成，不写入历史消息；提示词原文来自 `config/prompts/`。
"""

from __future__ import annotations

from .framework import (
    ConfigError,
    GradeBand,
    TutoringConfig,
    domain_ids,
    domain_templates_text,
    render_template,
)
from .problem import ProblemModel
from .state import Phase, SubtaskStatus, TutorState

_PHASE_LABELS: dict[Phase, str] = {
    Phase.idle: "空闲（没有正在辅导的题目）",
    Phase.tutoring: "辅导中",
    Phase.extension: "可选拓展",
    Phase.completed: "已完成",
}

_SUBTASK_STATUS_LABELS: dict[SubtaskStatus, str] = {
    SubtaskStatus.pending: "待开始",
    SubtaskStatus.active: "进行中",
    SubtaskStatus.completed: "已完成",
}


def _grade_band_or_error(cfg: TutoringConfig, grade_band: str) -> GradeBand:
    band = cfg.grade_bands.get(grade_band)
    if band is None:
        raise ConfigError(
            f"grade_bands.yaml 中没有学段 {grade_band!r}；"
            f"可用：{'、'.join(cfg.grade_bands)}"
        )
    return band


def _idle_block() -> str:
    return (
        "## 当前辅导状态\n\n"
        "当前没有正在辅导的题目；学生发来题目时调用 `analyze_problem`。"
    )


def _relation_lines(state: TutorState, problem: ProblemModel) -> list[str]:
    established: set[str] = set()
    for subtask_state in state.subtasks.values():
        established.update(subtask_state.established)

    lines = ["- 关系（按前提顺序）："]
    if not problem.relations:
        lines.append("  - （无）")
        return lines
    for relation in problem.relations:
        status = "已建立" if relation.id in established else "未建立"
        lines.append(
            f"  - {relation.id} [{relation.kind}]（{status}）：{relation.text}"
        )
    return lines


def _subtask_lines(state: TutorState, problem: ProblemModel) -> list[str]:
    lines = ["- 子任务："]
    if not problem.subtasks:
        lines.append("  - （无）")
        return lines
    for subtask in problem.subtasks:
        subtask_state = state.subtasks.get(subtask.id)
        status = (
            _SUBTASK_STATUS_LABELS[subtask_state.status]
            if subtask_state is not None
            else _SUBTASK_STATUS_LABELS[SubtaskStatus.pending]
        )
        tags = [status]
        if subtask.id == state.active_subtask_id:
            tags.append("当前")
        if subtask.optional:
            tags.append("可选")
        lines.append(
            f"  - {subtask.id} {subtask.title}（{'，'.join(tags)}）："
            f"目标 {subtask.goal}；完成标准 {subtask.completion_criteria}"
        )
    return lines


def _last_decision_lines(state: TutorState) -> list[str]:
    lines = ["- 上一轮决策："]
    decision = state.last_decision
    if decision is None:
        lines.append("  尚无（本回合是该题的第一个子任务或刚进入该题）。")
        return lines

    lines.append(f"  - 动作：{decision.action}（{decision.action_name}）")
    if decision.subtask_id:
        title = f" {decision.subtask_title}" if decision.subtask_title else ""
        lines.append(f"  - 子任务：{decision.subtask_id}{title}")
    lines.append(f"  - 目标：{decision.target or '（未指定）'}")
    lines.append(f"  - 允许的最高支持等级：{decision.max_support_level}")
    must_not_reveal = "；".join(decision.must_not_reveal) or "（无）"
    lines.append(f"  - 不得透露：{must_not_reveal}")
    if decision.notes:
        lines.append(f"  - 备注：{'；'.join(decision.notes)}")
    if decision.action in ("ask_reasoning", "decline_probe"):
        lines.append(
            "  - 注意：上一轮学生只报了答案，未判断对错；"
            "不要把它当作已建立或已否定的结论。"
        )
    return lines


def _problem_state_block(state: TutorState, problem: ProblemModel) -> str:
    lines = [
        "## 当前辅导状态",
        "",
        f"- 阶段：{_PHASE_LABELS[Phase(state.phase)]}",
        f"- 题目原文：{problem.statement}",
        f"- 已知：{'；'.join(problem.givens) if problem.givens else '（无）'}",
        f"- 所求：{problem.goal}",
    ]

    answer = problem.answer.text
    if problem.answer.latex and problem.answer.latex not in answer:
        answer = f"{answer}（LaTeX：${problem.answer.latex}$）"
    lines.append(f"- 最终答案：{answer}（仅供你参考，不得直接告诉学生）")

    lines.append("- 参考解法（仅供你参考，不得直接告诉学生）：")
    if problem.reference_solution.strip():
        for solution_line in problem.reference_solution.strip().splitlines():
            lines.append(f"  > {solution_line}")
    else:
        lines.append("  > （无）")

    lines.extend(_relation_lines(state, problem))
    lines.extend(_subtask_lines(state, problem))
    lines.extend(_last_decision_lines(state))

    if state.phase is Phase.completed:
        lines.append("")
        lines.append(
            "题目已完成；学生若愿意尝试拓展，调用 `record_diagnosis` 并把 "
            "subtask_id 设为拓展子任务 id；学生发来新题则调用 `analyze_problem`。"
        )
        pending_optional = [
            subtask.id for subtask in problem.subtasks if subtask.optional
            and (
                state.subtasks.get(subtask.id) is None
                or state.subtasks[subtask.id].status is SubtaskStatus.pending
            )
        ]
        if pending_optional:
            lines.append(
                f"可选拓展子任务：{'、'.join(pending_optional)}。"
            )
    else:
        active_id = state.active_subtask_id or "（当前子任务）"
        lines.append("")
        lines.append(
            f"学生下一次回复后，先调用 `record_diagnosis`（subtask_id={active_id}），"
            "再写回复。"
        )

    return "\n".join(lines)


def _state_block(
    state: TutorState, problem: ProblemModel | None
) -> str:
    if Phase(state.phase) is Phase.idle:
        return _idle_block()
    if problem is None:
        return (
            "## 当前辅导状态\n\n"
            f"- 阶段：{_PHASE_LABELS[Phase(state.phase)]}\n"
            "- 题目模型缺失；如果学生发来新题，调用 `analyze_problem`。"
        )
    return _problem_state_block(state, problem)


def build_tutor_system_prompt(
    cfg: TutoringConfig,
    *,
    grade: int,
    grade_band: str,
    state: TutorState,
    problem: ProblemModel | None,
) -> str:
    """填充 `tutor_system.md`，生成当前回合的辅导系统提示词。"""

    band = _grade_band_or_error(cfg, grade_band)
    values = {
        "grade_band_name": band.name,
        "grade": str(grade),
        "grade_band_style": band.style.strip(),
        "max_question_sentences": str(band.max_question_sentences),
        "tutor_state": _state_block(state, problem),
    }
    return render_template(cfg.tutor_system, values)


def build_analyzer_prompt(
    cfg: TutoringConfig, *, grade: int, grade_band: str
) -> str:
    """填充 `analyzer.md`，供 `analyze_problem` 使用。"""

    band = _grade_band_or_error(cfg, grade_band)
    values = {
        "grade_band_name": band.name,
        "grade": str(grade),
        "domain_ids": "、".join(domain_ids(cfg, grade_band)),
        "domain_templates": domain_templates_text(cfg, grade_band),
    }
    return render_template(cfg.analyzer, values)


def build_solver_check_prompt(cfg: TutoringConfig, *, statement: str) -> str:
    """填充 `solver_check.md`，供独立求解复核使用。"""

    return render_template(cfg.solver_check, {"statement": statement})

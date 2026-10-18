"""决策规则引擎：把状态、题目模型与本轮诊断映射成下一步动作。

实现 `docs/architecture.md` 4.4 的优先级。所有函数是纯函数：不修改入参，
不调用模型，不访问网络或数据库。
"""

from __future__ import annotations

from .decision import Decision
from .diagnosis import Diagnosis, Gap
from .framework import ConfigError, TutoringConfig
from .problem import ProblemModel, Relation, Subtask, relation_order
from .state import (
    MathStatus,
    Phase,
    SoloLevel,
    SubtaskState,
    SubtaskStatus,
    SupportLevel,
    TutorState,
    raise_support,
    solo_rank,
    support_rank,
)

# 这两个动作只是确认与过渡，不提供任何提示。
_NO_SUPPORT_ACTIONS = frozenset({"confirm_complete", "offer_extension"})


class PolicyError(Exception):
    """状态与诊断不匹配，无法继续决策。"""


def _find_subtask(problem: ProblemModel, subtask_id: str) -> Subtask | None:
    return next(
        (subtask for subtask in problem.subtasks if subtask.id == subtask_id), None
    )


def _find_relation(problem: ProblemModel, relation_id: str | None) -> Relation | None:
    if relation_id is None:
        return None
    return next(
        (relation for relation in problem.relations if relation.id == relation_id), None
    )


def _max_support(left: SupportLevel, right: SupportLevel) -> SupportLevel:
    return left if support_rank(left) >= support_rank(right) else right


def _higher_solo(
    current: SoloLevel | None, incoming: SoloLevel
) -> SoloLevel:
    """取两者中更高的 SOLO 层次；SU 不参与比较。"""

    if current is None:
        return incoming
    current_rank = solo_rank(current)
    incoming_rank = solo_rank(incoming)
    if current_rank is None:
        return incoming
    if incoming_rank is None:
        return current
    return incoming if incoming_rank > current_rank else current


def _established_anywhere(state: TutorState) -> set[str]:
    established: set[str] = set()
    for subtask_state in state.subtasks.values():
        established.update(subtask_state.established)
    return established


def _gap_sort_key(
    gap: Gap, index: int, order: dict[str, int]
) -> tuple[int, int, int]:
    """关系越靠前越优先；关系为空或未知的排最后；同序保持原顺序。"""

    if gap.relation_id is not None and gap.relation_id in order:
        return (0, order[gap.relation_id], index)
    return (1, 0, index)


def _has_other_incomplete_required(
    state: TutorState, problem: ProblemModel, current_subtask_id: str
) -> bool:
    """除当前子任务外，是否还有未完成的必做子任务。

    有，说明学生只报的答案不是"最后一步"，本轮按 answer probe 处理。
    """

    for subtask in problem.subtasks:
        if subtask.optional or subtask.id == current_subtask_id:
            continue
        subtask_state = state.subtasks.get(subtask.id)
        if subtask_state is None or subtask_state.status is not SubtaskStatus.completed:
            return True
    return False


def _must_not_reveal(
    state: TutorState, problem: ProblemModel, decision: Decision
) -> list[str]:
    """按 4.4 第 6 条计算本轮不得透露的内容。"""

    established_anywhere = _established_anywhere(state)
    if state.phase is Phase.completed:
        # 整题完成后只保留尚未建立的概括类关系，避免提前给出迁移结论。
        return [
            relation.text
            for relation in problem.relations
            if relation.kind == "generalization"
            and relation.id not in established_anywhere
        ]

    must_not_reveal = [f"最终答案：{problem.answer.text}"]
    must_not_reveal.extend(
        relation.text
        for relation in problem.relations
        if relation.kind != "generalization"
        and relation.id not in established_anywhere
    )
    if decision.max_support_level == SupportLevel.L3.value:
        allowed_relation = _find_relation(problem, decision.target_relation_id)
        if allowed_relation is not None:
            must_not_reveal = [
                text for text in must_not_reveal if text != allowed_relation.text
            ]
    return must_not_reveal


def _finalize(
    state: TutorState, decision: Decision, cfg: TutoringConfig
) -> tuple[TutorState, Decision]:
    """填入动作名称与引导说明，写回状态（4.4 第 8 步）。"""

    action_meta = cfg.framework.actions.get(decision.action)
    if action_meta is None:
        raise ConfigError(
            f"framework.yaml 中没有定义动作 {decision.action!r}"
        )
    decision.action_name = action_meta.name
    decision.guidance = action_meta.guidance
    decision.phase = state.phase.value
    state.last_decision = decision
    return state, decision


def start_problem(
    problem: ProblemModel, problem_id: int, cfg: TutoringConfig
) -> TutorState:
    """题目分析完成后初始化状态：第一个必做子任务进入 active。"""

    subtasks = {
        subtask.id: SubtaskState(subtask_id=subtask.id) for subtask in problem.subtasks
    }
    first_required = next(
        (subtask for subtask in problem.subtasks if not subtask.optional), None
    )
    if first_required is None:
        raise PolicyError("题目模型中没有必做子任务，无法开始辅导")

    subtasks[first_required.id].status = SubtaskStatus.active
    return TutorState(
        phase=Phase.tutoring,
        problem_id=problem_id,
        active_subtask_id=first_required.id,
        subtasks=subtasks,
        last_decision=None,
        framework_version=cfg.framework.version,
    )


def _complete_subtask(
    state: TutorState,
    problem: ProblemModel,
    diag_subtask: Subtask,
    decision: Decision,
) -> None:
    """处理当前子任务完成后的推进，并填好 `decision` 的动作与下一步。"""

    current_state = state.subtasks[diag_subtask.id]
    current_state.status = SubtaskStatus.completed
    current_state.stuck_turns = 0

    if state.phase is Phase.extension:
        next_subtask = next(
            (
                subtask
                for subtask in problem.subtasks
                if subtask.optional
                and state.subtasks.get(subtask.id) is not None
                and state.subtasks[subtask.id].status is SubtaskStatus.pending
            ),
            None,
        )
        if next_subtask is not None:
            state.subtasks[next_subtask.id].status = SubtaskStatus.active
            state.active_subtask_id = next_subtask.id
            decision.action = "confirm_complete"
            decision.next_subtask_id = next_subtask.id
            decision.next_subtask_title = next_subtask.title
            return

        # 拓展阶段没有更多可选子任务：整题结束。
        state.phase = Phase.completed
        state.active_subtask_id = None
        decision.action = "confirm_complete"
        return

    next_subtask = next(
        (
            subtask
            for subtask in problem.subtasks
            if not subtask.optional
            and state.subtasks.get(subtask.id) is not None
            and state.subtasks[subtask.id].status is SubtaskStatus.pending
        ),
        None,
    )
    if next_subtask is not None:
        state.subtasks[next_subtask.id].status = SubtaskStatus.active
        state.active_subtask_id = next_subtask.id
        decision.action = "confirm_complete"
        decision.next_subtask_id = next_subtask.id
        decision.next_subtask_title = next_subtask.title
        return

    # 必做子任务全部完成。
    state.phase = Phase.completed
    state.active_subtask_id = None
    pending_optional = [
        subtask
        for subtask in problem.subtasks
        if subtask.optional
        and state.subtasks.get(subtask.id) is not None
        and state.subtasks[subtask.id].status is SubtaskStatus.pending
    ]
    decision.action = "offer_extension"
    decision.has_extension = bool(pending_optional)
    if not pending_optional:
        decision.notes.append("全部完成，无拓展")


def decide(
    state: TutorState,
    problem: ProblemModel,
    diag: Diagnosis,
    cfg: TutoringConfig,
) -> tuple[TutorState, Decision]:
    """根据本轮诊断更新状态并给出决策。不修改 `state`、`problem`、`diag`。"""

    # 0. 前置条件：阶段与子任务必须匹配。
    if state.phase is Phase.idle:
        raise PolicyError("会话处于 idle 阶段，没有正在辅导的题目")

    diag_subtask = _find_subtask(problem, diag.subtask_id)
    if diag_subtask is None:
        raise PolicyError(
            f"诊断引用了题目中不存在的子任务 {diag.subtask_id}"
        )

    # 记录原始阶段：completed 阶段会被转换为 extension，probe 判定按转换前判断。
    original_phase = state.phase
    new_state = state.model_copy(deep=True)

    if new_state.phase is Phase.completed:
        if not diag_subtask.optional:
            raise PolicyError(
                f"题目已完成，只能对可选拓展子任务继续诊断；"
                f"{diag.subtask_id} 不是可选子任务"
            )
        optional_state = new_state.subtasks.get(diag_subtask.id)
        if optional_state is not None and optional_state.status is SubtaskStatus.completed:
            raise PolicyError(f"拓展子任务 {diag_subtask.id} 已完成")
        if optional_state is None:
            optional_state = SubtaskState(subtask_id=diag_subtask.id)
            new_state.subtasks[diag_subtask.id] = optional_state
        new_state.phase = Phase.extension
        new_state.active_subtask_id = diag_subtask.id
        optional_state.status = SubtaskStatus.active
    elif new_state.phase in (Phase.tutoring, Phase.extension):
        if new_state.active_subtask_id is None:
            raise PolicyError("当前阶段没有 active 子任务，状态不一致")
        if diag.subtask_id != new_state.active_subtask_id:
            raise PolicyError(
                f"诊断子任务 {diag.subtask_id} 与当前 active 子任务 "
                f"{new_state.active_subtask_id} 不一致"
            )
    else:  # pragma: no cover - Phase 只有四个取值
        raise PolicyError(f"未知的会话阶段：{new_state.phase}")

    sub = new_state.subtasks.get(diag.subtask_id)
    if sub is None:
        sub = SubtaskState(subtask_id=diag.subtask_id)
        new_state.subtasks[diag.subtask_id] = sub

    # 1. 记录本回合与证据的支持条件。
    sub.turns += 1
    sub.support_level = _max_support(sub.support_level, SupportLevel(diag.prior_support_level))

    decision = Decision(
        action="",
        action_name="",
        guidance="",
        phase=new_state.phase.value,
        subtask_id=diag_subtask.id,
        subtask_title=diag_subtask.title,
        subtask_goal=diag_subtask.goal,
    )

    # 在第 1 步之后、第 2 步之前：只报答案求对错（probe）。
    # 不算进展、不算求助、不判对错、不推进。
    is_probe = (
        diag.answer_only
        and original_phase is not Phase.completed
        and _has_other_incomplete_required(
            new_state, problem, diag_subtask.id
        )
    )
    if is_probe:
        new_state.answer_probes += 1
        if new_state.answer_probes <= cfg.policy.answer_probe_limit:
            decision.action = "ask_reasoning"
            decision.target = "请学生说明得到这个答案的过程或依据"
        else:
            decision.action = "decline_probe"
            decision.target = diag_subtask.goal
        decision.notes.append("answer_probe")

        # 支持上限保持上一轮已允许的水平，不因连续报答案而升级。
        current_allowed = sub.allowed_support or SupportLevel(
            cfg.policy.initial_support_level
        )
        decision.max_support_level = current_allowed.value
        decision.must_not_reveal = _must_not_reveal(
            new_state, problem, decision
        )
        decision.must_not_reveal.insert(
            0, "学生本轮所报答案是否正确（不要说对，也不要说错）"
        )
        return _finalize(new_state, decision, cfg)

    # 2. 更新证据、缺口与判定。只有 L0 证据才计入 independent_level。
    merged = set(sub.established) | set(diag.established_relations)
    sub.established = [
        relation.id for relation in problem.relations if relation.id in merged
    ]
    sub.missing = list(diag.gaps)
    sub.math_status = MathStatus(diag.math_status)
    sub.solo_level = SoloLevel(diag.solo_level)
    if sub.support_level is SupportLevel.L0 and diag.solo_level != SoloLevel.SU:
        sub.independent_level = _higher_solo(
            sub.independent_level, SoloLevel(diag.solo_level)
        )

    # 3. 连续无进展计数。
    if diag.made_progress:
        sub.stuck_turns = 0
    else:
        sub.stuck_turns += 1

    # 4. 完成判定：数学错误会阻止完成。
    established = set(sub.established)
    required_relations = set(diag_subtask.required_relations)
    completed = (
        diag.completion_met or required_relations.issubset(established)
    ) and sub.math_status is not MathStatus.blocking_error

    # 5. 按优先级选择动作。
    if sub.math_status is MathStatus.blocking_error:
        blocking_errors = [error for error in diag.errors if error.blocking]
        error = blocking_errors[0] if blocking_errors else (
            diag.errors[0] if diag.errors else None
        )
        if error is None:
            decision.target = "本步存在阻碍继续的错误，引导学生自己检查出错的那一步"
        elif error.quote.strip():
            decision.target = f"{error.description}（学生原文：{error.quote.strip()}）"
        else:
            decision.target = error.description
        decision.action = "correct_error"

    elif completed:
        _complete_subtask(new_state, problem, diag_subtask, decision)

    elif diag.solo_level == SoloLevel.SU:
        decision.action = "elicit_evidence"
        decision.target = diag_subtask.goal

    else:
        candidate_gaps = list(diag.gaps)
        if new_state.phase is not Phase.extension:
            candidate_gaps = [
                gap for gap in candidate_gaps if gap.gap_type != "generalization"
            ]

        if candidate_gaps:
            order = relation_order(problem)
            gap = min(
                enumerate(candidate_gaps),
                key=lambda pair: _gap_sort_key(pair[1], pair[0], order),
            )[1]
            gap_type = cfg.framework.gap_types.get(gap.gap_type)
            if gap_type is None:
                raise ConfigError(
                    f"framework.yaml 中没有定义缺口类型 {gap.gap_type!r}"
                )
            decision.action = gap_type.action
            decision.target = gap.description
            decision.target_relation_id = gap.relation_id
        else:
            decision.action = "build_relation"
            for relation_id in diag_subtask.required_relations:
                if relation_id not in established:
                    relation = _find_relation(problem, relation_id)
                    if relation is not None:
                        decision.target = relation.text
                        decision.target_relation_id = relation.id
                        break
            if not decision.target:
                # 必需关系都已建立但完成标准仍未达到，退回子任务目标。
                decision.target = diag_subtask.goal
                decision.notes.append("所有必需关系已建立，但尚未达到完成标准")

    # 6. 支持等级：只确定“允许的上限”，实际使用的等级由下一轮诊断记录。
    decision.max_support_level = SupportLevel.L0.value
    if decision.action not in _NO_SUPPORT_ACTIONS:
        base = _max_support(
            sub.support_level, SupportLevel(cfg.policy.initial_support_level)
        )
        if sub.allowed_support is not None:
            base = _max_support(base, sub.allowed_support)
        if sub.stuck_turns >= cfg.policy.stuck_turns_to_escalate:
            base = raise_support(
                base, 1, SupportLevel(cfg.policy.max_support_level)
            )
            sub.stuck_turns = 0
        if cfg.policy.help_request_escalates and diag.student_requested_help:
            base = raise_support(
                base, 1, SupportLevel(cfg.policy.max_support_level)
            )
        sub.allowed_support = base
        decision.max_support_level = base.value

    # 7. 学生不可见内容：最终答案与尚未建立的关系。
    decision.must_not_reveal = _must_not_reveal(new_state, problem, decision)

    # 8. 填入动作名称与引导说明，并写回状态。
    return _finalize(new_state, decision, cfg)


def general_decision(cfg: TutoringConfig) -> Decision:
    """idle 阶段的一般答疑决策：回应概念问题，必要时调用 analyze_problem。"""

    action_meta = cfg.framework.actions.get("answer_general")
    if action_meta is None:
        raise ConfigError("framework.yaml 中没有定义动作 'answer_general'")
    return Decision(
        action="answer_general",
        action_name=action_meta.name,
        guidance=action_meta.guidance,
        phase=Phase.idle.value,
    )

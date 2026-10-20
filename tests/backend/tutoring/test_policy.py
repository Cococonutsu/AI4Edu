"""规则引擎回归测试（`docs/architecture.md` 4.4、`docs/tutoring-framework.md`）。

题目用文档里那道反比例函数与相似三角形综合题的题目模型。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4edu.tutoring.diagnosis import Diagnosis, DiagnosisError, Gap, validate_against
from ai4edu.tutoring.framework import load_config
from ai4edu.tutoring.policy import PolicyError, decide, start_problem
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import (
    MathStatus,
    Phase,
    SubtaskStatus,
    SupportLevel,
)

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

PROBLEM = {
    "statement": "反比例函数综合题",
    "grade_band": "junior",
    "domain": "function_geometry",
    "givens": ["C 为 OA 中点", "CE⊥x 轴"],
    "goal": "求 k",
    "answer": {"text": "k = 5（选 C）", "latex": "k=5"},
    "relations": [
        {"id": "R1", "kind": "element", "text": "设 C(a, k/a)"},
        {"id": "R2", "kind": "relation", "text": "CE∥AB，△OCE∽△OAB"},
        {"id": "R3", "kind": "relation", "text": "中点与相似得 OB=2a、BE=a", "depends_on": ["R1", "R2"]},
        {"id": "R4", "kind": "relation", "text": "BD=k/(2a)", "depends_on": ["R3"]},
        {"id": "R5", "kind": "justification", "text": "S△BDE=k/4", "depends_on": ["R3", "R4"]},
        {"id": "R7", "kind": "generalization", "text": "OC/OA=t 时 S=k(1-t)/2", "depends_on": ["R5"]},
    ],
    "subtasks": [
        {"id": "T1", "stage": "represent", "title": "坐标表征", "goal": "表示 C 的坐标",
         "required_relations": ["R1"], "completion_criteria": "给出 C(a,k/a)", "optional": False},
        {"id": "T2", "stage": "relate", "title": "相似与线段", "goal": "得到 BE=a",
         "required_relations": ["R3"], "completion_criteria": "说明依据", "optional": False},
        {"id": "T5", "stage": "extend", "title": "条件变化", "goal": "一般化",
         "required_relations": ["R7"], "completion_criteria": "给出一般式", "optional": True},
    ],
    "reference_solution": "……",
}


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_DIR)


@pytest.fixture
def problem() -> ProblemModel:
    return ProblemModel.model_validate(PROBLEM)


def diag(**overrides) -> Diagnosis:
    base = dict(
        subtask_id="T1",
        evidence_quotes=["设C(a,k/a)"],
        established_relations=["R1"],
        solo_level="S1",
        made_progress=True,
        prior_support_level="L0",
    )
    base.update(overrides)
    return Diagnosis.model_validate(base)


def test_start_problem_activates_first_required(problem, cfg):
    state = start_problem(problem, problem_id=7, cfg=cfg)
    assert state.phase is Phase.tutoring
    assert state.active_subtask_id == "T1"
    assert state.subtasks["T5"].status.value == "pending"


def test_completion_advances_and_later_offers_extension(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(state, problem, diag(completion_met=True), cfg)
    assert decision.action == "confirm_complete"
    assert decision.next_subtask_id == "T2"
    assert state.active_subtask_id == "T2"
    assert decision.max_support_level == "L0"

    state, decision = decide(
        state, problem,
        diag(subtask_id="T2", established_relations=["R3"], solo_level="S3",
             evidence_quotes=["OB=2a，所以BE=a"], completion_met=True),
        cfg,
    )
    assert decision.action == "offer_extension"
    assert decision.has_extension is True
    assert state.phase is Phase.completed


def test_blocking_error_wins_over_completion(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(
        state, problem,
        diag(math_status="blocking_error", completion_met=True,
             errors=[DiagnosisError(quote="设C(a,k/a)", description="误认 D 与 C 等高", blocking=True)]),
        cfg,
    )
    assert decision.action == "correct_error"
    assert state.subtasks["T1"].status.value == "active"


def test_su_elicits_evidence_not_s0(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(
        state, problem,
        diag(evidence_quotes=[], established_relations=[], solo_level="SU",
             gaps=[Gap(gap_type="element", relation_id="R1", description="没有给出坐标")]),
        cfg,
    )
    assert decision.action == "elicit_evidence"


def test_gap_maps_to_action_and_earliest_relation_wins(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(
        state, problem,
        diag(solo_level="S2", established_relations=[],
             gaps=[
                 Gap(gap_type="justification", relation_id="R3", description="未说明相似依据"),
                 Gap(gap_type="element", relation_id="R1", description="没写 C 的坐标"),
             ]),
        cfg,
    )
    assert decision.action == "supplement_element"
    assert decision.target_relation_id == "R1"


def test_generalization_gap_ignored_outside_extension(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(
        state, problem,
        diag(solo_level="S2",
             gaps=[Gap(gap_type="generalization", relation_id="R7", description="没考虑一般情况")]),
        cfg,
    )
    assert decision.action != "transfer_boundary"


def test_support_escalates_after_stuck_turns(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    limit = cfg.policy.stuck_turns_to_escalate
    levels = []
    for _ in range(limit + 1):
        state, decision = decide(
            state, problem,
            diag(established_relations=[], evidence_quotes=["不会"], made_progress=False, solo_level="S1",
                 gaps=[Gap(gap_type="element", relation_id="R1", description="缺少坐标")],
                 prior_support_level="L0"),
            cfg,
        )
        levels.append(decision.max_support_level)
    assert levels[-1] > levels[0]
    assert levels[-1] <= cfg.policy.max_support_level


def test_escalated_support_does_not_drop_back(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    stuck = dict(established_relations=[], solo_level="S1", made_progress=False,
                 gaps=[Gap(gap_type="element", relation_id="R1", description="缺少坐标")])
    for _ in range(cfg.policy.stuck_turns_to_escalate):
        state, escalated = decide(state, problem, diag(**stuck), cfg)
    state, after = decide(state, problem, diag(**dict(stuck, made_progress=True)), cfg)
    assert after.max_support_level >= escalated.max_support_level


def test_supported_turns_do_not_count_as_independent(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    partial = dict(established_relations=[], solo_level="S1",
                   gaps=[Gap(gap_type="element", relation_id="R1", description="缺少坐标")])
    state, _ = decide(state, problem, diag(prior_support_level="L2", **partial), cfg)
    state, _ = decide(state, problem, diag(prior_support_level="L0", **partial), cfg)
    assert state.subtasks["T1"].independent_level is None


def test_must_not_reveal_lists_answer_and_unestablished_relations(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, decision = decide(state, problem, diag(solo_level="S1"), cfg)
    assert any("k = 5" in text for text in decision.must_not_reveal)
    assert any("S△BDE=k/4" in text for text in decision.must_not_reveal)


def test_decide_does_not_mutate_input(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    snapshot = state.model_dump()
    decide(state, problem, diag(completion_met=True), cfg)
    assert state.model_dump() == snapshot


def test_wrong_subtask_raises(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    with pytest.raises(PolicyError):
        decide(state, problem, diag(subtask_id="T2"), cfg)


def test_validate_against_rejects_fabricated_quote(problem):
    issues = validate_against(diag(evidence_quotes=["我觉得面积等于 k/4"]), problem, "设C(a,k/a)")
    assert issues


def test_problem_rejects_required_subtask_without_relations():
    payload = dict(PROBLEM)
    payload["subtasks"] = [dict(PROBLEM["subtasks"][0], required_relations=[])]
    with pytest.raises(ValueError, match="至少要关联一个关系"):
        ProblemModel.model_validate(payload)


# --- 只报答案求对错（answer probe）----------------------------------------


def test_answer_probe_asks_for_reasoning_without_progress(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    before = state.subtasks["T1"].model_copy(deep=True)
    allowed_before = state.subtasks["T1"].allowed_support

    state, decision = decide(state, problem, diag(answer_only=True), cfg)

    assert decision.action == "ask_reasoning"
    assert decision.target == "请学生说明得到这个答案的过程或依据"
    assert state.answer_probes == 1
    assert "answer_probe" in decision.notes
    assert decision.must_not_reveal[0] == (
        "学生本轮所报答案是否正确（不要说对，也不要说错）"
    )

    subtask = state.subtasks["T1"]
    assert subtask.status is SubtaskStatus.active
    assert subtask.stuck_turns == before.stuck_turns
    assert subtask.established == before.established
    assert subtask.missing == before.missing
    assert subtask.math_status is before.math_status
    assert subtask.solo_level is before.solo_level
    assert subtask.independent_level is before.independent_level
    assert subtask.allowed_support is allowed_before
    assert decision.max_support_level == cfg.policy.initial_support_level


def test_answer_probes_decline_after_limit(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    actions = []
    decisions = []
    for _ in range(cfg.policy.answer_probe_limit + 1):
        state, decision = decide(state, problem, diag(answer_only=True), cfg)
        actions.append(decision.action)
        decisions.append(decision)

    assert actions[:-1] == ["ask_reasoning"] * cfg.policy.answer_probe_limit
    assert actions[-1] == "decline_probe"
    assert state.answer_probes == cfg.policy.answer_probe_limit + 1
    assert decisions[-1].target == problem.subtasks[0].goal


def test_answer_probes_do_not_escalate_support(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    levels = []
    for _ in range(cfg.policy.answer_probe_limit + 1):
        state, decision = decide(state, problem, diag(answer_only=True), cfg)
        levels.append(decision.max_support_level)

    assert set(levels) == {cfg.policy.initial_support_level}
    assert state.subtasks["T1"].stuck_turns == 0
    assert state.subtasks["T1"].allowed_support is None


def test_answer_only_on_last_required_subtask_is_normal_completion(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, _ = decide(state, problem, diag(completion_met=True), cfg)
    assert state.active_subtask_id == "T2"

    state, decision = decide(
        state,
        problem,
        diag(
            subtask_id="T2",
            evidence_quotes=["OB=2a，所以BE=a"],
            established_relations=["R3"],
            solo_level="S3",
            completion_met=True,
            answer_only=True,
        ),
        cfg,
    )

    assert decision.action == "offer_extension"
    assert state.phase is Phase.completed
    assert state.answer_probes == 0


def test_completed_phase_does_not_treat_answer_only_as_probe(problem, cfg):
    state = start_problem(problem, problem_id=1, cfg=cfg)
    state, _ = decide(state, problem, diag(completion_met=True), cfg)
    state, _ = decide(
        state,
        problem,
        diag(
            subtask_id="T2",
            evidence_quotes=["OB=2a，所以BE=a"],
            established_relations=["R3"],
            solo_level="S3",
            completion_met=True,
        ),
        cfg,
    )
    assert state.phase is Phase.completed

    state, decision = decide(
        state,
        problem,
        diag(
            subtask_id="T5",
            evidence_quotes=["一般式"],
            established_relations=["R7"],
            solo_level="S4",
            completion_met=True,
            answer_only=True,
        ),
        cfg,
    )

    assert decision.action == "confirm_complete"
    assert state.answer_probes == 0

"""提示词组装与旧实现输出逐字一致（重构任务 G 的行为冻结基线）。

金样例目录 `golden/` 里的文件由旧 `tutoring/prompt_builder.py` 在重构
删除前生成；改动提示词模板时必须同步更新金样例并提升 `prompt_version`。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai4edu.prompts import load_reminders
from ai4edu.prompts.builder import build_system_prompt
from ai4edu.tutoring.decision import Decision
from ai4edu.tutoring.framework import load_config
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

PROBLEM = ProblemModel.model_validate(
    {
        "statement": "如图，C、D 在 y=k/x (k>0,x>0) 上，C 为 OA 中点，CE⊥x 轴于 E，"
        "S△BDE = 5/4，求 k。",
        "grade_band": "junior",
        "domain": "function_geometry",
        "givens": ["C、D 在 y=k/x (k>0,x>0) 上", "C 为 OA 中点"],
        "goal": "求 k",
        "answer": {"text": "k = 5（选 C）", "latex": "k=5"},
        "relations": [
            {"id": "R1", "kind": "element", "text": "设 C(a, k/a)"},
            {"id": "R2", "kind": "relation", "text": "CE∥AB，△OCE∽△OAB"},
            {
                "id": "R3",
                "kind": "relation",
                "text": "BE = a",
                "depends_on": ["R1", "R2"],
            },
            {
                "id": "R4",
                "kind": "justification",
                "text": "S△BDE = k/4",
                "depends_on": ["R3"],
            },
            {"id": "R5", "kind": "generalization", "text": "t 变化时的一般式"},
        ],
        "subtasks": [
            {
                "id": "T1",
                "stage": "represent",
                "title": "坐标表征",
                "goal": "写出 C 的坐标",
                "required_relations": ["R1"],
                "completion_criteria": "给出 C(a,k/a)",
                "optional": False,
            },
            {
                "id": "T2",
                "stage": "relate",
                "title": "相似与线段",
                "goal": "得到 BE=a",
                "required_relations": ["R2", "R3"],
                "completion_criteria": "说明依据并得到 BE=a",
                "optional": False,
            },
            {
                "id": "T5",
                "stage": "extend",
                "title": "条件变化",
                "goal": "一般化",
                "required_relations": ["R5"],
                "completion_criteria": "给出一般式",
                "optional": True,
            },
        ],
        "reference_solution": "第一行解法。\n第二行解法。",
    }
)


def _tutoring_state(*, probes: int = 1, decision: Decision | None) -> TutorState:
    state = TutorState.model_validate(
        {
            "phase": "tutoring",
            "problem_id": 7,
            "active_subtask_id": "T2",
            "subtasks": {
                "T1": {
                    "subtask_id": "T1",
                    "status": "completed",
                    "solo_level": "S3",
                    "math_status": "correct",
                    "established": ["R1"],
                    "missing": [],
                    "support_level": "L0",
                    "stuck_turns": 0,
                    "allowed_support": None,
                },
                "T2": {
                    "subtask_id": "T2",
                    "status": "active",
                    "solo_level": "S1",
                    "math_status": "unverified",
                    "established": [],
                    "missing": [],
                    "support_level": "L0",
                    "stuck_turns": 1,
                    "allowed_support": "L1",
                },
            },
            "answer_probes": probes,
        }
    )
    state.last_decision = decision
    return state


def _probe_decision() -> Decision:
    return Decision.model_validate(
        {
            "action": "ask_reasoning",
            "action_name": "询问依据",
            "guidance": "请学生说明依据",
            "phase": "tutoring",
            "subtask_id": "T2",
            "subtask_title": "相似与线段",
            "max_support_level": "L1",
            "must_not_reveal": ["最终答案", "R4 的面积关系"],
            "notes": ["学生只报了答案"],
        }
    )


def _gap_decision() -> Decision:
    return Decision.model_validate(
        {
            "action": "build_relation",
            "action_name": "关系建构",
            "guidance": "围绕缺口提问",
            "phase": "tutoring",
            "subtask_id": "T2",
            "subtask_title": "相似与线段",
            "target_gap": {
                "gap_type": "relation",
                "relation_id": "R2",
                "description": "未说明相似依据",
            },
            "max_support_level": "L1",
            "must_not_reveal": ["最终答案"],
            "notes": [],
        }
    )


def test_prompts_match_golden_baselines():
    # 文字已搬进 prompts/sections.py（对齐 cc），输出仍须与旧模板渲染逐字一致。
    cfg = load_config(CONFIG_DIR)

    st = _tutoring_state(decision=_probe_decision())
    st_gap = _tutoring_state(probes=0, decision=_gap_decision())
    st_none = _tutoring_state(decision=None)
    st_completed = TutorState.model_validate(
        st.model_dump() | {"phase": "completed", "active_subtask_id": None}
    )
    st_completed.subtasks["T2"].status = "completed"
    st_missing = TutorState.model_validate({"phase": "tutoring", "problem_id": 7})

    cases = {
        "tutor_idle.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=TutorState.idle(), problem=None,
        ),
        "tutor_missing_problem.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=st_missing, problem=None,
        ),
        "tutor_tutoring.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=st, problem=PROBLEM,
        ),
        "tutor_tutoring_gap.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=st_gap, problem=PROBLEM,
        ),
        "tutor_no_decision.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=st_none, problem=PROBLEM,
        ),
        "tutor_completed.txt": build_system_prompt(
            cfg, grade=8, grade_band="junior",
            state=st_completed, problem=PROBLEM,
        ),
        "tutor_senior.txt": build_system_prompt(
            cfg, grade=10, grade_band="senior",
            state=st, problem=PROBLEM,
        ),
    }

    for name, text in cases.items():
        golden = (GOLDEN_DIR / name).read_text(encoding="utf-8")
        assert text == golden, f"{name} 与基线不一致（提示词发生了意外改动）"


def test_diagnosis_criteria_rendered_from_config():
    cfg = load_config(CONFIG_DIR)
    prompt = build_system_prompt(
        cfg,
        grade=8,
        grade_band="junior",
        state=TutorState.idle(),
        problem=None,
    )

    for level_id, level in cfg.framework.solo_levels.items():
        assert f"- {level_id} {level.name}：{level.criterion}" in prompt

    for gap_id, gap in cfg.framework.gap_types.items():
        assert f"- {gap_id} {gap.name}" in prompt

    for level_id in ("L0", "L1", "L2", "L3"):
        assert f"- {level_id}：{cfg.framework.support_levels[level_id]}" in prompt

    assert "L4" not in prompt


def test_diagnosis_criteria_follow_config_changes(tmp_path: Path):
    cfg = load_config(CONFIG_DIR)
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, config_dir)

    framework_path = config_dir / "framework" / "framework.yaml"
    text = framework_path.read_text(encoding="utf-8")
    old_criterion = cfg.framework.solo_levels["S2"].criterion
    new_criterion = "测试用的多点结构判据（来自修改后的配置）"
    assert old_criterion in text
    framework_path.write_text(
        text.replace(old_criterion, new_criterion), encoding="utf-8"
    )

    changed = load_config(config_dir)
    prompt = build_system_prompt(
        changed,
        grade=8,
        grade_band="junior",
        state=TutorState.idle(),
        problem=None,
    )

    assert new_criterion in prompt
    assert old_criterion not in prompt


def test_reminders_format_missing_placeholder_raises():
    from ai4edu.tutoring.framework import ConfigError

    reminders = load_reminders(CONFIG_DIR)

    with pytest.raises(ConfigError):
        reminders.text("bad_tool_arguments")  # 缺 {error}、{name} 取值


def test_problem_decomposition_section_in_tutor_prompt():
    """读题与拆题由辅导老师自己完成：拆题规则和本学段领域模板在系统提示词里。"""

    cfg = load_config(CONFIG_DIR)
    prompt = build_system_prompt(
        cfg,
        grade=8,
        grade_band="junior",
        state=TutorState.idle(),
        problem=None,
    )

    assert "## 读题与拆题" in prompt
    assert "### 领域模板" in prompt
    assert "{{domain_ids}}" not in prompt
    assert "{{domain_templates}}" not in prompt
    assert "function_geometry" in prompt

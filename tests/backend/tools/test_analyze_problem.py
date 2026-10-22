"""`analyze_problem`：接收老师拆好的题目模型；不调用模型，学段来自账号。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai4edu.models.contracts import StudentProfile
from ai4edu.prompts import Reminders
from ai4edu.session.store import TurnStore
from ai4edu.storage.repos import problems
from ai4edu.tools.analyze_problem import analyze_problem
from ai4edu.tools.base import ToolContext
from ai4edu.tutoring.framework import load_config
from ai4edu.tutoring.state import Phase, TutorState
from fakes import FakeLLMClient

pytestmark = pytest.mark.asyncio

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

PROBLEM = {
    "statement": "反比例函数综合题",
    "domain": "function_geometry",
    "givens": ["C 为 OA 中点"],
    "goal": "求 k",
    "answer": {"text": "k=5（选 C）", "latex": "k=5"},
    "relations": [
        {"id": "R1", "kind": "element", "text": "设 C(a, k/a)"},
        {"id": "R2", "kind": "relation", "text": "BE = a", "depends_on": ["R1"]},
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
            "title": "线段关系",
            "goal": "得到 BE",
            "required_relations": ["R2"],
            "completion_criteria": "得到 BE=a",
            "optional": False,
        },
    ],
    "reference_solution": "略",
}


async def _context(seed, db_session, tmp_path):
    user, conversation_id = await seed(grade_band="junior", grade=8)
    client = FakeLLMClient([])
    ctx = ToolContext(
        store=TurnStore(db_session, user_id=user.id, conversation_id=conversation_id),
        config=load_config(CONFIG_DIR),
        reminders=Reminders(),
        user=StudentProfile(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            grade=user.grade,
            grade_band=user.grade_band,
            role=user.role,
        ),
        conversation_id=conversation_id,
        turn_id="turn-1",
        student_text="如图，求 k 的值。",
        state=TutorState.idle(),
    )
    return ctx, client, user, conversation_id


async def test_grade_band_comes_from_account(seed, db_session, tmp_path):
    """回归：错误记录 #5 —— 模型把学段写成“初中”导致校验失败。"""

    ctx, _, user, conversation_id = await _context(seed, db_session, tmp_path)

    result = await analyze_problem.execute({**PROBLEM, "grade_band": "初中"}, ctx)

    assert result.is_error is False, result.content
    rows = await problems.list_for_conversation(db_session, conversation_id, user.id)
    assert rows[-1].model_json["grade_band"] == "junior"
    assert ctx.problem is not None
    assert ctx.problem.grade_band == "junior"


async def test_schema_does_not_ask_model_for_grade_band():
    schema = analyze_problem.input_schema
    assert "grade_band" not in schema["properties"]
    assert "grade_band" not in schema.get("required", [])
    assert "$defs" not in json.dumps(schema)


async def test_analyze_makes_no_model_call_and_starts_tutoring(seed, db_session, tmp_path):
    """读题与拆题由老师自己完成，本工具不再调用模型，也不做验算。"""

    ctx, client, user, conversation_id = await _context(seed, db_session, tmp_path)

    result = await analyze_problem.execute(dict(PROBLEM), ctx)

    assert result.is_error is False, result.content
    assert client.calls == []
    data = json.loads(result.content)
    assert data["current_subtask_id"] == "T1"
    assert [item["id"] for item in data["subtasks"]] == ["T1", "T2"]
    assert "reference_solution" not in result.content
    assert ctx.state.phase == Phase.tutoring
    rows = await problems.list_for_conversation(db_session, conversation_id, user.id)
    assert rows[-1].confidence == "unverified"


async def test_invalid_problem_returns_field_reason(seed, db_session, tmp_path):
    ctx, client, user, conversation_id = await _context(seed, db_session, tmp_path)
    broken = {key: value for key, value in PROBLEM.items() if key != "subtasks"}

    result = await analyze_problem.execute(broken, ctx)

    assert result.is_error is True
    assert "题目模型不合格" in result.content
    assert "子任务" in result.content
    assert client.calls == []
    assert ctx.problem is None
    assert await problems.list_for_conversation(db_session, conversation_id, user.id) == []

"""`answer_directly`：辅导中核对必须说明学生是否展示了过程。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import ai4edu.tools.answer_directly as answer_directly_module
from ai4edu.tutoring.state import Phase, TutorState

# 显式标记：从仓库根目录收集测试时 backend/pyproject.toml 的 asyncio_mode 不生效。
pytestmark = pytest.mark.asyncio

_EXPECTED_REJECTION = (
    "辅导进行中，学生只报了答案。请改为调用 record_diagnosis"
    "（answer_only=true），按返回的决策回复，不要判断对错。"
)


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _context(phase: Phase) -> SimpleNamespace:
    return SimpleNamespace(
        db=_FakeDb(),
        state=TutorState(phase=phase),
        problem=None,
        conversation_id=1,
        user_message_id=None,
        pending_reply=None,
    )


@pytest.fixture
def recorded(monkeypatch):
    calls = []

    async def fake_add(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(answer_directly_module.evidence, "add", fake_add)
    return calls


async def test_check_without_work_is_rejected_in_tutoring(recorded):
    ctx = _context(Phase.tutoring)

    result = await answer_directly_module.answer_directly.execute(
        {"kind": "check", "reply": "对，k=5。", "has_work": False}, ctx
    )

    assert result.is_error is True
    assert result.content == _EXPECTED_REJECTION
    assert recorded == []
    assert ctx.pending_reply is None


async def test_check_without_has_work_is_rejected_in_tutoring(recorded):
    ctx = _context(Phase.tutoring)

    result = await answer_directly_module.answer_directly.execute(
        {"kind": "check", "reply": "对，k=5。"}, ctx
    )

    assert result.is_error is True
    assert "has_work" in result.content
    assert recorded == []


async def test_check_with_work_is_allowed_in_extension(recorded):
    ctx = _context(Phase.extension)

    result = await answer_directly_module.answer_directly.execute(
        {"kind": "check", "reply": "对，因为两边相等。", "has_work": True}, ctx
    )

    assert result.is_error is False
    assert ctx.pending_reply == "对，因为两边相等。"
    assert len(recorded) == 1


async def test_idle_check_does_not_require_has_work(recorded):
    ctx = _context(Phase.idle)

    result = await answer_directly_module.answer_directly.execute(
        {"kind": "check", "reply": "对，k=5。"}, ctx
    )

    assert result.is_error is False
    assert ctx.pending_reply == "对，k=5。"
    assert len(recorded) == 1

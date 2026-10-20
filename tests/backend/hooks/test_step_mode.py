"""`choose_step_mode`：按回合事实决定本步是否思考（`docs/architecture.md` 3.2）。"""

from __future__ import annotations

from ai4edu.hooks.tutoring_hooks import TurnFacts, choose_step_mode


def facts(**overrides) -> TurnFacts:
    values = dict(
        step=1,
        has_diagnosis=False,
        has_analyze=False,
        last_step_tool_error=False,
    )
    values.update(overrides)
    return TurnFacts(**values)


def test_first_step_thinks():
    assert choose_step_mode(facts(step=1)) == ("on", "auto")


def test_after_diagnosis_thinking_turns_off():
    assert choose_step_mode(facts(step=2, has_diagnosis=True)) == ("off", "auto")


def test_after_analyze_thinking_turns_off():
    assert choose_step_mode(facts(step=2, has_analyze=True)) == ("off", "auto")


def test_tool_choice_is_always_auto():
    for mode in (
        facts(step=1),
        facts(step=3, has_diagnosis=True),
        facts(step=2, last_step_tool_error=True),
    ):
        assert choose_step_mode(mode)[1] == "auto"


def test_after_tool_error_thinking_stays_on():
    """工具报错后需要模型修正重试，判断还没做完，保持思考。"""

    assert choose_step_mode(facts(step=2, last_step_tool_error=True)) == (
        "on",
        "auto",
    )


def test_later_steps_without_diagnosis_keep_thinking():
    assert choose_step_mode(facts(step=3)) == ("on", "auto")

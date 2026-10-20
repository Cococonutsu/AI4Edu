"""内部消息序列的规范化与校验（`docs/architecture.md` 3.1）。"""

from __future__ import annotations

import copy
import logging
import random

import pytest

from ai4edu.models.content import (
    ImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from ai4edu.models.messages import (
    Message,
    MessageSequenceError,
    normalize_messages,
    prepare_messages,
    validate_messages,
)


def user(*blocks) -> Message:
    return Message(role="user", content=list(blocks))


def assistant(*blocks) -> Message:
    return Message(role="assistant", content=list(blocks))


def call(call_id: str, name: str = "record_diagnosis") -> ToolUseBlock:
    return ToolUseBlock(id=call_id, name=name, input={})


def tool(call_id: str, content: str = "结果") -> Message:
    return Message(
        role="tool",
        content=[ToolResultBlock(tool_use_id=call_id, content=content)],
    )


def _text(message: Message) -> str:
    return "".join(
        block.text for block in message.content if isinstance(block, TextBlock)
    )


def test_complete_sequence_passes_unchanged():
    messages = [
        user(TextBlock(text="这道题怎么做")),
        assistant(call("call_1"), call("call_2")),
        tool("call_1", "第一步"),
        tool("call_2", "第二步"),
        assistant(TextBlock(text="我们看第一步")),
        user(TextBlock(text="好的")),
    ]

    normalized, fixes = normalize_messages(messages)

    assert [(m.role, m.content) for m in normalized] == [
        (m.role, m.content) for m in messages
    ]
    assert fixes == []
    validate_messages(normalized)


def test_consecutive_users_are_merged_with_image_content():
    messages = [
        user(TextBlock(text="先看这张图")),
        user(ImageBlock(attachment_id=12), TextBlock(text="图中的角是多少")),
    ]

    normalized, fixes = normalize_messages(messages)

    assert len(normalized) == 1
    assert normalized[0].role == "user"
    assert normalized[0].content == [
        TextBlock(text="先看这张图"),
        ImageBlock(attachment_id=12),
        TextBlock(text="图中的角是多少"),
    ]
    assert any("user" in fix for fix in fixes)


def test_consecutive_users_text_joined_with_blank_line():
    messages = [
        user(TextBlock(text="第一句")),
        user(TextBlock(text="第二句")),
    ]

    normalized, fixes = normalize_messages(messages)

    assert normalized == [user(TextBlock(text="第一句\n\n第二句"))]
    assert any("user" in fix for fix in fixes)


def test_consecutive_assistants_keep_text_thinking_and_tool_calls():
    messages = [
        user(TextBlock(text="开始")),
        assistant(
            ThinkingBlock(text="思考一"), TextBlock(text="先算一下"), call("call_1")
        ),
        assistant(
            ThinkingBlock(text="思考二"), TextBlock(text="再算一下"), call("call_2")
        ),
        tool("call_1"),
        tool("call_2"),
        user(TextBlock(text="继续")),
    ]

    normalized, fixes = normalize_messages(messages)

    assistants = [m for m in normalized if m.role == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].content == [
        ThinkingBlock(text="思考一\n\n思考二"),
        TextBlock(text="先算一下\n\n再算一下"),
        call("call_1"),
        call("call_2"),
    ]
    assert any("assistant" in fix for fix in fixes)


def test_empty_assistant_removed_and_neighbouring_users_merged():
    messages = [
        user(TextBlock(text="第一句")),
        assistant(),
        user(TextBlock(text="第二句")),
    ]

    normalized, fixes = normalize_messages(messages)

    assert normalized == [user(TextBlock(text="第一句\n\n第二句"))]
    assert any("空" in fix for fix in fixes)
    assert any("user" in fix for fix in fixes)


def test_thinking_only_assistant_is_removed():
    messages = [
        user(TextBlock(text="题目")),
        assistant(ThinkingBlock(text="只想不说")),
        user(TextBlock(text="继续")),
    ]

    normalized, fixes = normalize_messages(messages)

    assert normalized == [user(TextBlock(text="题目\n\n继续"))]
    assert any("空" in fix for fix in fixes)


def test_missing_tool_result_is_added():
    messages = [
        user(TextBlock(text="题目")),
        assistant(call("call_1"), call("call_2")),
        tool("call_1", "只有这一条"),
        user(TextBlock(text="继续")),
    ]

    normalized, fixes = normalize_messages(messages)

    tool_messages = [m for m in normalized if m.role == "tool"]
    assert [m.content[0].tool_use_id for m in tool_messages] == [
        "call_1",
        "call_2",
    ]
    assert tool_messages[1].content[0].content == "工具未执行（回合被中断）"
    assert any("call_2" in fix for fix in fixes)
    validate_messages(normalized)


def test_duplicate_and_unknown_tool_results_are_removed():
    messages = [
        user(TextBlock(text="题目")),
        assistant(call("call_1"), call("call_2")),
        tool("call_1", "第一次"),
        tool("call_1", "重复"),
        tool("call_unknown", "不认识"),
        tool("call_2", "第二次"),
        user(TextBlock(text="继续")),
    ]

    normalized, fixes = normalize_messages(messages)

    tool_messages = [m for m in normalized if m.role == "tool"]
    assert [m.content[0].tool_use_id for m in tool_messages] == [
        "call_1",
        "call_2",
    ]
    assert [m.content[0].content for m in tool_messages] == ["第一次", "第二次"]
    assert any("重复" in fix for fix in fixes)
    assert any("找不到" in fix for fix in fixes)
    validate_messages(normalized)


def test_reversed_tool_results_are_reordered():
    messages = [
        user(TextBlock(text="题目")),
        assistant(call("call_1"), call("call_2")),
        tool("call_2", "第二步"),
        tool("call_1", "第一步"),
        user(TextBlock(text="继续")),
    ]

    normalized, fixes = normalize_messages(messages)

    tool_messages = [m for m in normalized if m.role == "tool"]
    assert [m.content[0].tool_use_id for m in tool_messages] == [
        "call_1",
        "call_2",
    ]
    assert [m.content[0].content for m in tool_messages] == ["第一步", "第二步"]
    assert any("重排" in fix for fix in fixes)


@pytest.mark.parametrize("first", ["assistant", "tool"])
def test_leading_assistant_or_tool_is_removed(first):
    if first == "assistant":
        messages = [
            assistant(TextBlock(text="不该出现")),
            user(TextBlock(text="学生")),
        ]
    else:
        messages = [tool("call_x"), user(TextBlock(text="学生"))]

    normalized, fixes = normalize_messages(messages)

    assert normalized == [user(TextBlock(text="学生"))]
    assert any(fix.startswith("删除了开头") for fix in fixes)


def test_unknown_role_is_rejected_by_validate():
    messages = [
        Message(role="system", content=[TextBlock(text="系统")]),  # type: ignore[arg-type]
        user(TextBlock(text="问题")),
    ]

    with pytest.raises(MessageSequenceError, match="role"):
        validate_messages(messages)


def test_validate_rejects_last_assistant():
    messages = [
        user(TextBlock(text="问题")),
        assistant(TextBlock(text="回答")),
    ]

    with pytest.raises(MessageSequenceError, match="最后一条"):
        validate_messages(messages)


def test_validate_rejects_empty_list():
    with pytest.raises(MessageSequenceError):
        validate_messages([])


def test_validate_rejects_missing_leading_user():
    messages = [assistant(call("call_1")), tool("call_1")]

    with pytest.raises(MessageSequenceError):
        validate_messages(messages)


def test_normalize_does_not_modify_input():
    messages = [
        user(TextBlock(text="第一句")),
        user(TextBlock(text="第二句")),
        assistant(call("call_1")),
        tool("call_1"),
        user(TextBlock(text="继续")),
    ]
    snapshot = copy.deepcopy(
        [(m.role, [type(b) for b in m.content]) for m in messages]
    )

    normalize_messages(messages)

    assert [(m.role, [type(b) for b in m.content]) for m in messages] == snapshot


def test_prepare_messages_logs_warning_when_repaired(caplog):
    caplog.set_level(logging.WARNING, logger="ai4edu.models.messages")

    prepare_messages(
        [
            user(TextBlock(text="第一句")),
            user(TextBlock(text="第二句")),
        ]
    )

    assert "消息序列已修复" in caplog.text
    assert "user" in caplog.text


def _random_messages(rng: random.Random) -> list[Message]:
    roles = ("user", "assistant", "tool")
    call_ids = [f"call_{index}" for index in range(4)]
    messages: list[Message] = []

    for _ in range(rng.randint(2, 9)):
        role = rng.choice(roles)
        if role == "user":
            if rng.random() < 0.3:
                messages.append(
                    user(
                        TextBlock(text="带图的问题"),
                        ImageBlock(attachment_id=3),
                    )
                )
            else:
                messages.append(user(TextBlock(text=f"学生{rng.randint(0, 9)}")))
        elif role == "assistant":
            uses = [
                call(rng.choice(call_ids)) for _ in range(rng.randint(0, 2))
            ]
            blocks: list = []
            if rng.random() < 0.4:
                blocks.append(ThinkingBlock(text=f"思考{rng.randint(0, 9)}"))
            if rng.choice([True, False]):
                blocks.append(TextBlock(text=f"老师{rng.randint(0, 9)}"))
            blocks.extend(uses)
            messages.append(assistant(*blocks))
        else:
            messages.append(
                tool(rng.choice(call_ids + ["call_unknown"]), f"结果{rng.randint(0, 9)}")
            )

    # 至少一条 user，且最后一条是 user。
    messages.append(user(TextBlock(text="保证存在的学生消息")))
    messages.insert(
        rng.randint(0, len(messages) - 1),
        user(TextBlock(text="另一条学生消息")),
    )
    rng.shuffle(messages)
    last_user = max(
        index for index, message in enumerate(messages)
        if message.role == "user"
    )
    messages.append(messages.pop(last_user))
    return messages


def test_prepare_messages_always_produces_valid_sequence_for_random_history():
    rng = random.Random(20241018)

    for _ in range(300):
        messages = _random_messages(rng)
        normalized = prepare_messages(messages)
        validate_messages(normalized)

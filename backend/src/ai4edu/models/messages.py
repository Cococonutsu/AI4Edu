"""内部消息与消息序列的规范化、校验（`docs/architecture.md` 3.1 节）。

所有模型调用在发出请求前都必须经过 `prepare_messages()`：先修复历史里
可能存在的残缺序列，再校验；校验不通过就抛 `MessageSequenceError`，
不发请求。规范化在**内部 `Message` 对象**上做，system 提示词不属于消息
列表，单独放在 `ModelRequest.system`。

本模块是纯逻辑，只使用标准库与本包的 `content.py`，不认识辅导业务。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from ai4edu.models.content import (
    Block,
    ImageBlock,
    InlineImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    blocks_from_json,
    blocks_to_json,
)

from ai4edu.utils.errors import MessageSequenceError

logger = logging.getLogger(__name__)

MISSING_TOOL_RESULT = "工具未执行（回合被中断）"

Role = Literal["user", "assistant", "tool"]
_ROLES = frozenset({"user", "assistant", "tool"})


@dataclass
class Message:
    role: Role
    content: list[Block] = field(default_factory=list)
    turn_id: str | None = None
    db_id: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> "Message":
        return cls(
            role=str(row.role),  # type: ignore[arg-type]
            content=blocks_from_json(row.content_json),
            turn_id=row.turn_id,
            db_id=row.id,
        )

    def to_append_dict(self) -> dict[str, Any]:
        """转成 `session.store.append_messages` 需要的字典。"""

        return {
            "role": self.role,
            "content_json": blocks_to_json(self.content),
            "turn_id": self.turn_id,
        }

    def image_attachment_ids(self) -> list[int]:
        return [
            block.attachment_id
            for block in self.content
            if isinstance(block, ImageBlock)
        ]


def _texts_of(message: Message) -> list[str]:
    return [
        block.text for block in message.content if isinstance(block, TextBlock)
    ]


def _text_of(message: Message) -> str:
    return "".join(_texts_of(message))


def _thinking_of(message: Message) -> list[str]:
    return [
        block.text
        for block in message.content
        if isinstance(block, ThinkingBlock)
    ]


def _tool_uses_of(message: Message) -> list[ToolUseBlock]:
    return [
        block for block in message.content if isinstance(block, ToolUseBlock)
    ]


def _tool_results_of(message: Message) -> list[ToolResultBlock]:
    return [
        block for block in message.content if isinstance(block, ToolResultBlock)
    ]


def _has_image(message: Message) -> bool:
    return any(
        isinstance(block, (ImageBlock, InlineImageBlock))
        for block in message.content
    )


def _join_text(left: str, right: str) -> str:
    if left and right:
        return left + "\n\n" + right
    return left or right


def _merge_user_messages(first: Message, second: Message) -> Message:
    """合并两条 user：纯文字用空行连接；任何一边带图时拼接内容列表。"""

    if not _has_image(first) and not _has_image(second):
        text = _join_text(_text_of(first), _text_of(second))
        blocks: list[Block] = [TextBlock(text=text)] if text else []
    else:
        blocks = [*first.content, *second.content]
    return Message(role="user", content=blocks, turn_id=first.turn_id, db_id=first.db_id)


def _merge_assistant_messages(first: Message, second: Message) -> Message:
    """合并两条 assistant：正文与思考用空行连接，工具调用依次拼接。"""

    blocks: list[Block] = []
    thinking = _join_text(
        "".join(_thinking_of(first)), "".join(_thinking_of(second))
    )
    if thinking:
        blocks.append(ThinkingBlock(text=thinking))
    text = _join_text(_text_of(first), _text_of(second))
    if text:
        blocks.append(TextBlock(text=text))
    blocks.extend(_tool_uses_of(first))
    blocks.extend(_tool_uses_of(second))
    return Message(
        role="assistant", content=blocks, turn_id=first.turn_id, db_id=first.db_id
    )


def _assistant_is_empty(message: Message) -> bool:
    if _tool_uses_of(message):
        return False
    return not _text_of(message).strip()


def _record_fix(fixes: list[str], text: str) -> None:
    if text not in fixes:
        fixes.append(text)


def _dedupe_tool_uses(message: Message, fixes: list[str]) -> bool:
    uses = _tool_uses_of(message)
    if not uses:
        return False

    seen: set[str] = set()
    kept: list[Block] = []
    changed = False
    for block in message.content:
        if isinstance(block, ToolUseBlock):
            if block.id in seen:
                _record_fix(fixes, f"删除了重复的工具调用 {block.id}")
                changed = True
                continue
            seen.add(block.id)
        kept.append(block)

    if not changed:
        return False
    message.content = kept
    return True


def _pair_tool_results(
    messages: list[Message], fixes: list[str]
) -> list[Message]:
    """把工具结果与调用配对：补缺失、删重复/未知/错位、按调用顺序排列。"""

    result: list[Message] = []
    index = 0
    while index < len(messages):
        message = messages[index]

        if message.role == "assistant":
            uses = _tool_uses_of(message)
            if not uses:
                result.append(message)
                index += 1
                continue

            result.append(message)
            call_ids = [use.id for use in uses]

            gathered: list[tuple[str, ToolResultBlock]] = []
            cursor = index + 1
            while cursor < len(messages) and messages[cursor].role == "tool":
                for block in _tool_results_of(messages[cursor]):
                    gathered.append((block.tool_use_id, block))
                cursor += 1

            first_by_id: dict[str, ToolResultBlock] = {}
            for tool_use_id, block in gathered:
                if tool_use_id not in call_ids:
                    _record_fix(
                        fixes, f"删除了找不到对应调用的工具结果 {tool_use_id}"
                    )
                    continue
                if tool_use_id in first_by_id:
                    _record_fix(fixes, f"删除了重复的工具结果 {tool_use_id}")
                    continue
                first_by_id[tool_use_id] = block

            gathered_order: list[str] = []
            for tool_use_id, _ in gathered:
                if (
                    tool_use_id in first_by_id
                    and tool_use_id not in gathered_order
                ):
                    gathered_order.append(tool_use_id)
            expected_order = [
                tool_use_id
                for tool_use_id in call_ids
                if tool_use_id in first_by_id
            ]
            if gathered_order != expected_order:
                _record_fix(fixes, "按工具调用顺序重排了结果")

            for tool_use_id in call_ids:
                block = first_by_id.get(tool_use_id)
                if block is not None:
                    result.append(
                        Message(
                            role="tool",
                            content=[block],
                            turn_id=message.turn_id,
                        )
                    )
                else:
                    result.append(
                        Message(
                            role="tool",
                            content=[
                                ToolResultBlock(
                                    tool_use_id=tool_use_id,
                                    content=MISSING_TOOL_RESULT,
                                    # 结果缺失说明执行被中断：按错误结果补，
                                    # 模型能从 is_error 看出这不是正常返回。
                                    is_error=True,
                                    status_label="未执行",
                                )
                            ],
                            turn_id=message.turn_id,
                        )
                    )
                    _record_fix(fixes, f"为工具调用 {tool_use_id} 补了错误结果")

            index = cursor
            continue

        if message.role == "tool":
            blocks = _tool_results_of(message)
            tool_use_id = blocks[0].tool_use_id if blocks else ""
            _record_fix(
                fixes, f"删除了位置不对的工具结果 {tool_use_id}".rstrip()
            )
            index += 1
            continue

        result.append(message)
        index += 1

    return result


def normalize_messages(messages: list[Message]) -> tuple[list[Message], list[str]]:
    """按 3.1 节表格的顺序修复消息序列，返回新列表与修复记录。

    不修改入参；修复规则反复执行直到序列不再变化。
    """

    result = [
        Message(
            role=m.role,
            content=list(m.content),
            turn_id=m.turn_id,
            db_id=m.db_id,
        )
        for m in messages
    ]
    fixes: list[str] = []

    changed = True
    while changed:
        changed = False

        # 1. 第一条消息必须是 user：删除开头的 assistant / tool。
        while result and result[0].role in ("assistant", "tool"):
            removed = result.pop(0)
            _record_fix(fixes, f"删除了开头的 {removed.role} 消息")
            changed = True

        # 2. 不能连续两条 user：合并。
        index = 0
        while index + 1 < len(result):
            if result[index].role == "user" and result[index + 1].role == "user":
                result[index : index + 2] = [
                    _merge_user_messages(result[index], result[index + 1])
                ]
                _record_fix(fixes, "合并了连续的 user 消息")
                changed = True
            else:
                index += 1

        # 3. 不能连续两条 assistant：合并。
        index = 0
        while index + 1 < len(result):
            if (
                result[index].role == "assistant"
                and result[index + 1].role == "assistant"
            ):
                result[index : index + 2] = [
                    _merge_assistant_messages(result[index], result[index + 1])
                ]
                _record_fix(fixes, "合并了连续的 assistant 消息")
                changed = True
            else:
                index += 1

        # 4. assistant 不能为空：删除。删除后外层循环会再次合并相邻消息。
        index = 0
        while index < len(result):
            if result[index].role == "assistant" and _assistant_is_empty(
                result[index]
            ):
                result.pop(index)
                _record_fix(fixes, "删除了空的 assistant 消息")
                changed = True
            else:
                index += 1

        # 5. 同一条 assistant 内工具调用 id 不重复。
        for message in result:
            if message.role == "assistant" and _dedupe_tool_uses(message, fixes):
                changed = True

        # 6. 每个工具调用有且只有一条结果，紧跟在 assistant 之后并按调用顺序。
        paired = _pair_tool_results(result, fixes)
        if paired != result:
            changed = True
        result = paired

    return result, fixes


def validate_messages(messages: list[Message]) -> None:
    """按 3.1 节表格逐条校验，不满足时抛 `MessageSequenceError`。"""

    if not messages:
        raise MessageSequenceError("消息列表为空：至少需要一条 user 消息")

    for index, message in enumerate(messages):
        if message.role not in _ROLES:
            raise MessageSequenceError(
                f"第 {index + 1} 条消息的 role {message.role!r} 不合法"
            )

    # 1. 第一条消息必须是 user。
    if messages[0].role != "user":
        raise MessageSequenceError(
            "第 1 条消息违反了“第一条消息必须是 user”的规则"
        )

    for index in range(1, len(messages)):
        previous_role = messages[index - 1].role
        role = messages[index].role

        # 2. 不能连续两条 user。
        if role == "user" and previous_role == "user":
            raise MessageSequenceError(
                f"第 {index + 1} 条消息违反了“不能连续两条 user”的规则"
            )

        # 3. 不能连续两条 assistant（中间隔着工具结果的除外）。
        if role == "assistant" and previous_role == "assistant":
            raise MessageSequenceError(
                f"第 {index + 1} 条消息违反了“不能连续两条 assistant”的规则"
            )

    # 4. assistant 不能为空。
    for index, message in enumerate(messages):
        if message.role == "assistant" and _assistant_is_empty(message):
            raise MessageSequenceError(
                f"第 {index + 1} 条消息违反了“assistant 不能为空”的规则"
            )

    # 5. 同一条 assistant 内工具调用 id 不重复。
    for index, message in enumerate(messages):
        if message.role != "assistant":
            continue
        seen: set[str] = set()
        for use in _tool_uses_of(message):
            if use.id in seen:
                raise MessageSequenceError(
                    f"第 {index + 1} 条消息违反了"
                    f"“工具调用 id 不能重复”（{use.id}）的规则"
                )
            seen.add(use.id)

    # 6. 工具结果必须紧跟对应的 assistant，并按调用顺序排列。
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "assistant":
            uses = _tool_uses_of(message)
            if uses:
                call_ids = [use.id for use in uses]
                flat_results: list[ToolResultBlock] = []
                cursor = index + 1
                while cursor < len(messages) and messages[cursor].role == "tool":
                    flat_results.extend(_tool_results_of(messages[cursor]))
                    cursor += 1
                actual_ids = [block.tool_use_id for block in flat_results]
                if actual_ids != call_ids:
                    raise MessageSequenceError(
                        f"第 {index + 2} 条消息违反了"
                        f"“工具结果紧跟调用并按调用顺序排列”"
                        f"（期望 {call_ids}，实际 {actual_ids}）的规则"
                    )
                index = cursor
                continue
            index += 1
            continue

        if message.role == "tool":
            raise MessageSequenceError(
                f"第 {index + 1} 条消息违反了"
                "“tool 结果必须紧跟带工具调用的 assistant”的规则"
            )

        index += 1

    # 7. 最后一条必须是 user 或 tool。
    last_role = messages[-1].role
    if last_role not in ("user", "tool"):
        raise MessageSequenceError(
            f"第 {len(messages)} 条消息违反了"
            f"“最后一条必须是 user 或 tool”（当前是 {last_role}）的规则"
        )

    # 8. 规范化后至少有一条 user。
    if not any(message.role == "user" for message in messages):
        raise MessageSequenceError("消息序列中至少需要一条 user 消息")


def prepare_messages(messages: list[Message]) -> list[Message]:
    """规范化并校验；有修复时记 warning。返回新的消息列表。"""

    normalized, fixes = normalize_messages(messages)
    if fixes:
        logger.warning("消息序列已修复：%s", "；".join(fixes))
    validate_messages(normalized)
    return normalized


__all__ = [
    "MISSING_TOOL_RESULT",
    "Message",
    "MessageSequenceError",
    "normalize_messages",
    "prepare_messages",
    "validate_messages",
]

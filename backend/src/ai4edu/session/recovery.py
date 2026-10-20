"""加载历史时修复残缺回合。

上一回合如果在工具执行中被停止，数据库里会留下“assistant 发起了工具
调用、但没有结果”的残缺序列。`repair_history` 在内存里为缺失的结果补上
“工具未执行（回合被中断）”，让每次模型请求拿到完整序列；数据库原文不动。
发请求前的完整规范化与校验仍由 `models/messages.prepare_messages()` 负责，
两边的修复是幂等的。
"""

from __future__ import annotations

import logging

from ai4edu.models.content import ToolResultBlock, ToolUseBlock
from ai4edu.models.messages import MISSING_TOOL_RESULT, Message

logger = logging.getLogger(__name__)


def repair_history(messages: list[Message]) -> list[Message]:
    """为没有结果的工具调用补上占位结果；不修改入参。"""

    result: list[Message] = []
    repairs = 0
    index = 0
    while index < len(messages):
        message = messages[index]

        if message.role == "assistant":
            use_ids = [
                block.id
                for block in message.content
                if isinstance(block, ToolUseBlock)
            ]
            if not use_ids:
                result.append(message)
                index += 1
                continue

            result.append(message)
            answered: set[str] = set()
            cursor = index + 1
            while cursor < len(messages) and messages[cursor].role == "tool":
                answered.update(
                    block.tool_use_id
                    for block in messages[cursor].content
                    if isinstance(block, ToolResultBlock)
                )
                result.append(messages[cursor])
                cursor += 1

            for use_id in use_ids:
                if use_id not in answered:
                    result.append(
                        Message(
                            role="tool",
                            content=[
                                ToolResultBlock(
                                    tool_use_id=use_id,
                                    content=MISSING_TOOL_RESULT,
                                )
                            ],
                            turn_id=message.turn_id,
                        )
                    )
                    repairs += 1

            index = cursor
            continue

        result.append(message)
        index += 1

    if repairs:
        logger.warning(
            "加载历史时修复了残缺回合：补了 %d 条缺失的工具结果", repairs
        )
    return result


__all__ = ["repair_history"]

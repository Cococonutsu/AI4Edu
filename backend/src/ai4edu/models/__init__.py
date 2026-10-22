"""内部数据结构：内容块与消息，以及消息序列的规范化校验。

本包不导入 `ai4edu` 的其他子包。
"""

from ai4edu.utils.errors import MessageSequenceError
from ai4edu.models.content import (
    Block,
    ImageBlock,
    InlineImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    block_from_json,
    block_to_json,
    blocks_from_json,
    blocks_to_json,
)
from ai4edu.models.messages import (
    MISSING_TOOL_RESULT,
    Message,
    normalize_messages,
    prepare_messages,
    validate_messages,
)

__all__ = [
    "Block",
    "ImageBlock",
    "InlineImageBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
    "MISSING_TOOL_RESULT",
    "Message",
    "MessageSequenceError",
    "block_from_json",
    "block_to_json",
    "blocks_from_json",
    "blocks_to_json",
    "normalize_messages",
    "prepare_messages",
    "validate_messages",
]

"""智能体循环使用的消息对象，以及它与数据库行的互转。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ai4edu.agent.content import Block, ImageBlock, blocks_from_json, blocks_to_json


@dataclass
class AgentMessage:
    role: Literal["user", "assistant", "tool"]
    content: list[Block] = field(default_factory=list)
    turn_id: str | None = None
    db_id: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> "AgentMessage":
        return cls(
            role=str(row.role),  # type: ignore[arg-type]
            content=blocks_from_json(row.content_json),
            turn_id=row.turn_id,
            db_id=row.id,
        )

    def to_append_dict(self) -> dict[str, Any]:
        """转成 `storage.repos.messages.append_messages` 需要的字典。"""

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

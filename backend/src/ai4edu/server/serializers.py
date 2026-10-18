"""内部消息 → 学生可见消息（`docs/architecture.md` 7.2 节）。

只输出用户/助手正文与图片引用；思考内容、工具调用与结果一律过滤。
同一 `turn_id` 的助手消息合并为一条可见消息。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from ai4edu.server.schemas import VisibleAttachment, VisibleMessage
from ai4edu.storage.models import Message


def _blocks(content: object) -> list[dict]:
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, dict):
        return [content]
    return []


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def visible_messages(rows: Sequence[Message]) -> list[VisibleMessage]:
    visible: list[VisibleMessage] = []
    pending: dict | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is None:
            return
        text = "".join(pending["texts"])
        if text.strip():
            visible.append(
                VisibleMessage(
                    id=pending["id"],
                    role="assistant",
                    text=text,
                    attachments=[],
                    created_at=_utc(pending["created_at"]),
                )
            )
        pending = None

    for row in sorted(rows, key=lambda item: item.seq):
        blocks = _blocks(row.content_json)

        if row.role == "user":
            flush_pending()
            texts: list[str] = []
            attachments: list[VisibleAttachment] = []
            seen: set[int] = set()
            for block in blocks:
                block_type = block.get("type")
                if block_type == "text":
                    texts.append(str(block.get("text") or ""))
                elif block_type == "image":
                    raw_id = block.get("attachment_id")
                    if raw_id is None:
                        continue
                    attachment_id = int(raw_id)
                    if attachment_id in seen:
                        continue
                    seen.add(attachment_id)
                    attachments.append(
                        VisibleAttachment(
                            id=attachment_id,
                            url=f"/api/attachments/{attachment_id}",
                        )
                    )
            text = "".join(texts)
            if not text.strip() and not attachments:
                continue
            visible.append(
                VisibleMessage(
                    id=row.id,
                    role="user",
                    text=text,
                    attachments=attachments,
                    created_at=_utc(row.created_at),
                )
            )

        elif row.role == "assistant":
            turn_key = row.turn_id or f"__message_{row.id}"
            if pending is not None and pending["turn_key"] != turn_key:
                flush_pending()
            if pending is None:
                pending = {"turn_key": turn_key, "texts": [], "id": row.id}
            for block in blocks:
                if block.get("type") == "text":
                    pending["texts"].append(str(block.get("text") or ""))
            # 该回合最后一条 assistant 消息决定可见消息的 id 与时间。
            pending["id"] = row.id
            pending["created_at"] = row.created_at

        # role == "tool" 与其他未知角色：不返回，也不打断助手回合的合并。

    flush_pending()
    return visible

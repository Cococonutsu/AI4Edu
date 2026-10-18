"""按表划分的数据访问函数。"""

from ai4edu.storage.repos import (
    attachments,
    conversations,
    evidence,
    llm_calls,
    messages,
    problems,
    users,
)

__all__ = [
    "attachments",
    "conversations",
    "evidence",
    "llm_calls",
    "messages",
    "problems",
    "users",
]

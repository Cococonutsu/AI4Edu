"""会话持久化编排：回合存储与历史修复。

只有本包（以及 `auth/`、`server/routes` 的简单增删改查）可以调用
`storage/repos`；`core/`、`hooks/`、`tools/` 通过 `TurnStore` 读写。
"""

from ai4edu.session.recovery import repair_history
from ai4edu.session.store import TurnStore

__all__ = ["TurnStore", "repair_history"]

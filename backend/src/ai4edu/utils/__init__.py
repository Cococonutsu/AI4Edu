"""零依赖的公共工具：项目内最底层，只放各包共用的定义（对齐 cc 的 utils/）。

本包不导入 `ai4edu` 的任何其他子包；任何包都可以安全地导入本包。
目前只有 `errors.py`（应用异常树）。新增文件须保持零依赖。
"""

from ai4edu.utils.errors import AI4EduError

__all__ = ["AI4EduError"]

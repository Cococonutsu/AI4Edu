"""`check_math`：把模型的符号/数值核查请求交给 SymPy 子进程。"""

from __future__ import annotations

import json
from typing import Any

from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tools.math_engine import run as run_math

_MAX_OPERATIONS = 10


class CheckMathTool(BaseTool):
    name = "check_math"
    description = (
        "用符号计算核对数学式子。可以直接传学生原来的写法"
        "（支持 4ac、k/2a、²、√、LaTeX 等），工具会自动规范化；"
        "若解析失败，请根据上下文改写后重试，不要要求学生改写法。"
        "支持三种操作："
        "equal（判断 left 与 right 是否相等）、"
        "solve（解 equation=0，可给 expect 检查是否在解集中）、"
        "evaluate（把 expr 中的变量按 subs 代入求值）。"
        "结果中的 normalized 是规范化后的表达式，便于核对系统如何理解学生的写法。"
    )
    running_label = "正在核对计算…"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "maxItems": _MAX_OPERATIONS,
                "description": "要核对的操作，最多 10 个。",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["equal", "solve", "evaluate"],
                            "description": "操作类型。",
                        },
                        "left": {"type": "string", "description": "equal：左边表达式。"},
                        "right": {"type": "string", "description": "equal：右边表达式。"},
                        "equation": {
                            "type": "string",
                            "description": "solve：令其等于 0 的表达式。",
                        },
                        "symbol": {
                            "type": "string",
                            "description": "solve：未知量，例如 k。",
                        },
                        "expect": {
                            "type": "string",
                            "description": "solve：期望的解，用于检查是否在解集中。",
                        },
                        "expr": {"type": "string", "description": "evaluate：待求值的表达式。"},
                        "subs": {
                            "type": "object",
                            "description": "evaluate：变量名到取值的映射。",
                        },
                    },
                    "required": ["kind"],
                },
            }
        },
        "required": ["operations"],
    }

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        operations = input.get("operations")
        if not isinstance(operations, list) or not operations:
            return ToolResult(
                content="operations 必须是非空数组",
                is_error=True,
                status_label="核对失败",
            )
        if len(operations) > _MAX_OPERATIONS:
            return ToolResult(
                content=f"一次最多核对 {_MAX_OPERATIONS} 个操作",
                is_error=True,
                status_label="核对失败",
            )

        results = await run_math(operations)
        return ToolResult(
            content=json.dumps({"results": results}, ensure_ascii=False),
            status_label="核对完成",
        )


check_math = CheckMathTool()

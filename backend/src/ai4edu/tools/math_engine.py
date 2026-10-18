"""在受控子进程中运行 SymPy 计算。

模型或学生给出的表达式绝不进入主进程的 `eval`。子进程使用 `-I` 隔离模式；
若该模式下找不到 `ai4edu` 包，则用 `-c` + `runpy` 直接加载 worker 文件。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_WORKER_PATH = Path(__file__).with_name("sympy_worker.py")
_DEFAULT_TIMEOUT = 5.0


def _error_result(message: str) -> dict[str, Any]:
    return {"ok": False, "result": "", "error": message, "normalized": {}}


async def _communicate(
    command: list[str], payload: bytes, timeout: float
) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(payload), timeout=timeout
        )
    except (asyncio.TimeoutError, TimeoutError):
        process.kill()
        await process.wait()
        raise TimeoutError from None
    return process.returncode or 0, stdout, stderr


def _fallback_command() -> list[str]:
    boot = (
        "import runpy; "
        f"runpy.run_path({str(_WORKER_PATH)!r}, run_name='__main__')"
    )
    return [sys.executable, "-I", "-c", boot]


async def run(
    operations: list[dict[str, Any]], timeout: float = _DEFAULT_TIMEOUT
) -> list[dict[str, Any]]:
    """执行一组操作，返回与输入等长的结果列表；超时或崩溃时逐项返回错误。"""

    if not operations:
        return []

    payload = json.dumps({"operations": operations}, ensure_ascii=False).encode("utf-8")

    module_command = [sys.executable, "-I", "-m", "ai4edu.tools.sympy_worker"]
    try:
        returncode, stdout, stderr = await _communicate(
            module_command, payload, timeout
        )
        if returncode != 0 and b"No module named" in stderr:
            returncode, stdout, stderr = await _communicate(
                _fallback_command(), payload, timeout
            )
    except TimeoutError:
        return [_error_result("计算超时") for _ in operations]
    except Exception as exc:  # 子进程无法启动等
        return [_error_result(f"计算失败：{exc}") for _ in operations]

    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:300]
        return [
            _error_result(f"计算进程异常退出：{detail or returncode}")
            for _ in operations
        ]

    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return [_error_result("计算结果不是合法 JSON") for _ in operations]

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        message = data.get("error") if isinstance(data, dict) else None
        return [
            _error_result(str(message or "计算进程没有返回结果"))
            for _ in operations
        ]

    normalized: list[dict[str, Any]] = []
    for index in range(len(operations)):
        item = results[index] if index < len(results) else None
        if not isinstance(item, dict):
            normalized.append(_error_result("缺少计算结果"))
            continue
        raw_normalized = item.get("normalized")
        normalized.append(
            {
                "ok": bool(item.get("ok")),
                "result": str(item.get("result") or ""),
                "error": item.get("error"),
                "normalized": (
                    raw_normalized if isinstance(raw_normalized, dict) else {}
                ),
            }
        )
    return normalized

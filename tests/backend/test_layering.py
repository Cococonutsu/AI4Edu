"""依赖方向与职责边界的 AST 检查（根 `AGENTS.md` 硬性规则 1、10）。

- `core/query_loop.py` 只依赖 `models/`、`core/events.py` 与传入的参数；
- 只有 `api/glm.py`、`api/deepseek.py`、`api/openai_compat.py`、`api/client.py`
  可以 `import openai`；
- `ai4edu.api` 是厂商实现层：src 中除 `api/` 自身外，只有
  `core/query_engine.py`（经 `client.py` 创建 Provider）可以导入它，
  其余模块只使用 `models/contracts` 里的契约类型；
- `models/` 不导入 `ai4edu` 的其他子包；
- 只有 `session/`、`auth/`、`server/routes/`、`cli/` 与 `storage/` 自身
  可以调用 `storage/repos`。
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "backend" / "src" / "ai4edu"


def _python_files() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_query_loop_depends_only_on_parameters():
    path = SRC / "core" / "query_loop.py"
    forbidden_prefixes = (
        "openai",
        "ai4edu.api",
        "ai4edu.storage",
        "ai4edu.tutoring",
        "ai4edu.prompts",
        "ai4edu.tools",
        "ai4edu.session",
        "ai4edu.server",
        "ai4edu.hooks",
    )
    for module in _imports_of(path):
        assert not module.startswith(forbidden_prefixes), (
            f"core/query_loop.py 不得导入 {module}（只依赖传入的参数）"
        )

    source = path.read_text(encoding="utf-8")
    for tool_name in ("analyze_problem", "record_diagnosis", "draw_figure"):
        assert tool_name not in source, (
            f"core/query_loop.py 源码中不得出现具体工具名 {tool_name}"
        )


def test_only_api_provider_modules_import_openai():
    allowed = {
        SRC / "api" / "glm.py",
        SRC / "api" / "deepseek.py",
        SRC / "api" / "openai_compat.py",
        SRC / "api" / "client.py",
    }
    for path in _python_files():
        modules = _imports_of(path)
        offender = next(
            (m for m in modules if m == "openai" or m.startswith("openai.")),
            None,
        )
        if offender:
            assert path in allowed, (
                f"{path.relative_to(SRC)} 导入了 {offender}；"
                "只有 api/glm.py、api/deepseek.py、api/openai_compat.py "
                "与 api/client.py 可以导入厂商 SDK"
            )


def test_only_query_engine_imports_api():
    allowed = {SRC / "core" / "query_engine.py"}
    for path in _python_files():
        if (path.parent.relative_to(SRC)).parts[0:1] == ("api",):
            continue
        offender = next(
            (m for m in _imports_of(path) if m.startswith("ai4edu.api")),
            None,
        )
        if offender:
            assert path in allowed, (
                f"{path.relative_to(SRC)} 导入了 {offender}；"
                "ai4edu.api 是厂商实现层，src 中只有 core/query_engine.py"
                "（经 client.py 创建 Provider）可以导入它，"
                "其余模块使用 models/contracts 里的契约类型"
            )


def test_models_imports_no_other_subpackage():
    for path in (SRC / "models").glob("*.py"):
        for module in _imports_of(path):
            allowed = (
                module.startswith("ai4edu.models")
                # utils/ 是零依赖的最底层公共定义包（异常树），等同项目内标准库。
                or module.startswith("ai4edu.utils")
                or not module.startswith("ai4edu")
            )
            assert allowed, (
                f"{path.relative_to(SRC)} 导入了 {module}；"
                "models/ 不导入 ai4edu 的其他子包"
            )


def test_only_session_auth_routes_cli_use_repos():
    allowed_prefixes = (
        "ai4edu.session",
        "ai4edu.auth",
        "ai4edu.server.routes",
        "ai4edu.cli",
        "ai4edu.storage",
    )
    for path in _python_files():
        parts = path.relative_to(SRC).parts
        own_package = "ai4edu." + ".".join(parts[:-1]) if len(parts) > 1 else "ai4edu"
        if own_package.startswith(allowed_prefixes):
            continue
        for module in _imports_of(path):
            assert not (
                module == "ai4edu.storage.repos"
                or module.startswith("ai4edu.storage.repos.")
            ), (
                f"{path.relative_to(SRC)} 导入了 {module}；"
                "storage/repos 只有 session/、auth/、server/routes/、cli/ 可以调用"
            )

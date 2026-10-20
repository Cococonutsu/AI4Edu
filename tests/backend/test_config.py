"""仓库根目录定位。"""

from __future__ import annotations

from ai4edu.config import _is_repo_root


def test_repo_root_found_without_agents_md(tmp_path):
    """回归：错误记录 #13 —— 删除 AGENTS.md 后找不到配置目录。"""

    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "config" / "framework").mkdir(parents=True)

    assert _is_repo_root(repo) is True

    incomplete = tmp_path / "incomplete"
    (incomplete / "backend").mkdir(parents=True)
    assert _is_repo_root(incomplete) is False

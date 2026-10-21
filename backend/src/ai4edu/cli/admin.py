"""管理员命令行：`ai4edu-admin`。

v1 不开放注册，账号由这里创建。所有命令运行前自动建表。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ai4edu.auth.passwords import hash_password
from ai4edu.storage.db import async_session, init_db
from ai4edu.storage.repos import users
from ai4edu.tutoring.framework import grade_band_for


class AdminError(Exception):
    """面向管理员的可读错误。"""


async def _create_user(session: AsyncSession, args: argparse.Namespace) -> None:
    username = args.username.strip()
    if not username:
        raise AdminError("用户名不能为空")
    if await users.get_by_username(session, username) is not None:
        raise AdminError(f"用户名 {username} 已存在")
    if not args.password:
        raise AdminError("密码不能为空")
    try:
        grade_band = grade_band_for(args.grade)
    except ValueError as exc:
        # 学段推导在 `tutoring/` 里是纯函数；命令行仍用 AdminError 报告。
        raise AdminError(str(exc)) from exc
    user = await users.create(
        session,
        username=username,
        password_hash=hash_password(args.password),
        display_name=(args.display_name or username).strip() or username,
        grade_band=grade_band,
        grade=args.grade,
        role=args.role,
    )
    print(f"已创建用户 {user.username}（id={user.id}，{user.grade_band}，年级 {user.grade}）")


async def _import_users(session: AsyncSession, args: argparse.Namespace) -> None:
    path: Path = args.csv
    if not path.is_file():
        raise AdminError(f"找不到文件：{path}")

    required = {"username", "password", "display_name", "grade"}
    created = 0
    skipped = 0
    failed = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise AdminError(f"CSV 缺少列：{', '.join(sorted(missing))}")
        for line_no, row in enumerate(reader, start=2):
            username = (row.get("username") or "").strip()
            password = row.get("password") or ""
            display_name = (row.get("display_name") or "").strip() or username
            grade_text = (row.get("grade") or "").strip()
            if not username or not password or not grade_text:
                print(f"第 {line_no} 行：缺少 username/password/grade，跳过")
                failed += 1
                continue
            try:
                grade = int(grade_text)
                grade_band = grade_band_for(grade)
            except (ValueError, AdminError) as exc:
                print(f"第 {line_no} 行：{exc}，跳过")
                failed += 1
                continue
            if await users.get_by_username(session, username) is not None:
                print(f"跳过：用户名 {username} 已存在")
                skipped += 1
                continue
            await users.create(
                session,
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
                grade_band=grade_band,
                grade=grade,
                role="student",
            )
            created += 1

    print(f"导入完成：新建 {created}，已存在跳过 {skipped}，失败 {failed}")


async def _list_users(session: AsyncSession, args: argparse.Namespace) -> None:
    rows = await users.list_all(session)
    if not rows:
        print("暂无用户")
        return
    print("id\tusername\tdisplay_name\tgrade\tgrade_band\trole\tactive")
    for user in rows:
        print(
            f"{user.id}\t{user.username}\t{user.display_name}\t{user.grade}\t"
            f"{user.grade_band}\t{user.role}\t{'yes' if user.is_active else 'no'}"
        )


async def _set_password(session: AsyncSession, args: argparse.Namespace) -> None:
    if not args.password:
        raise AdminError("密码不能为空")
    user = await users.set_password(session, args.username.strip(), hash_password(args.password))
    if user is None:
        raise AdminError(f"用户 {args.username} 不存在")
    print(f"已更新 {user.username} 的密码")


async def _deactivate(session: AsyncSession, args: argparse.Namespace) -> None:
    user = await users.set_active(session, args.username.strip(), False)
    if user is None:
        raise AdminError(f"用户 {args.username} 不存在")
    print(f"已停用 {user.username}")


async def _dispatch(session: AsyncSession, args: argparse.Namespace) -> None:
    handlers = {
        "create-user": _create_user,
        "import-users": _import_users,
        "list-users": _list_users,
        "set-password": _set_password,
        "deactivate": _deactivate,
    }
    await handlers[args.command](session, args)


async def _run(args: argparse.Namespace) -> None:
    await init_db()
    async with async_session() as session:
        try:
            await _dispatch(session, args)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai4edu-admin", description="AI4Edu 管理员命令")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-user", help="创建账号")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--grade", required=True, type=int, help="年级 1–12")
    create.add_argument("--display-name", default=None)
    create.add_argument("--role", choices=["student", "admin"], default="student")

    import_users = subparsers.add_parser("import-users", help="从 CSV 批量导入学生")
    import_users.add_argument("csv", type=Path, help="列：username,password,display_name,grade")

    subparsers.add_parser("list-users", help="列出账号")

    set_password = subparsers.add_parser("set-password", help="重设密码")
    set_password.add_argument("--username", required=True)
    set_password.add_argument("--password", required=True)

    deactivate = subparsers.add_parser("deactivate", help="停用账号")
    deactivate.add_argument("--username", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except AdminError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()

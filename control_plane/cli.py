"""Safe bootstrap commands for the authenticated management API."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .security import ValidationError
from .storage import AccountStore


def _password_from_terminal() -> str:
    first = getpass.getpass("管理员密码：")
    second = getpass.getpass("再次输入管理员密码：")
    if first != second:
        raise ValidationError("password_mismatch", "两次输入的密码不一致。")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=os.environ.get("APP_DATA_DIR", ".runtime/data"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("init-admin", help="在空账号池中建立唯一初始管理员")
    initialize.add_argument("--username", default="admin")
    initialize.add_argument(
        "--password-stdin",
        action="store_true",
        help="从标准输入读取一行密码；默认使用无回显交互输入",
    )
    args = parser.parse_args()
    store = AccountStore(Path(args.data_root))
    try:
        if args.command == "init-admin":
            password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else _password_from_terminal()
            account = store.bootstrap_admin(args.username, password)
            print(f"initial administrator created: {account['username']} ({account['id']})")
    except ValidationError as error:
        parser.error(error.message)


if __name__ == "__main__":
    main()

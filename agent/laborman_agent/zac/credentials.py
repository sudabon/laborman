"""zac のパスワードを macOS キーチェーンから読み出す。

パスワードはキーチェーンにだけ置き、設定ファイル・DB・ログ・実行履歴・通知・例外メッセージに出さない。
利用者は `security add-generic-password -s <service> -a <login_id> -w` で登録する。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

Runner = Callable[..., Any]
SECURITY_TIMEOUT_SECONDS = 10


def registration_hint(service: str, login_id: str) -> str:
    return f"security add-generic-password -s {service} -a {login_id or '<ログイン ID>'} -w"


def read_password(service: str, login_id: str, runner: Runner = subprocess.run) -> str | None:
    """キーチェーンからパスワードを読む。未登録・読めない場合は None。"""
    if not login_id:
        return None
    try:
        result = runner(
            ["security", "find-generic-password", "-s", service, "-a", login_id, "-w"],
            capture_output=True,
            text=True,
            check=False,
            timeout=SECURITY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    password = str(result.stdout).rstrip("\n")
    return password or None


def has_password(service: str, login_id: str, runner: Runner = subprocess.run) -> bool:
    return read_password(service, login_id, runner) is not None

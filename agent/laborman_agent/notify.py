from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Any

NOTIFICATION_TITLE = "laborman-agent"

Runner = Callable[..., Any]


def applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


def build_notification_command(message: str, title: str = NOTIFICATION_TITLE) -> list[str]:
    """macOS 通知のコマンド。メール本文や業務内容の詳細は渡さないこと（対象日と結果の要約のみ）。"""
    script = f"display notification {applescript_string(message)} with title {applescript_string(title)}"
    return ["osascript", "-e", script]


class Notifier:
    def __init__(self, enabled: bool = True, runner: Runner = subprocess.run) -> None:
        self.enabled = enabled and sys.platform == "darwin"
        self.runner = runner

    def notify(self, message: str) -> None:
        if not self.enabled:
            return
        try:
            self.runner(build_notification_command(message), check=False, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            # 通知に失敗しても本処理の結果は変えない
            pass

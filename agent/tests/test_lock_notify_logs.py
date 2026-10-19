from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from laborman_agent.lock import LockBusyError, acquire_lock
from laborman_agent.logs import ensure_private_dir, purge_expired, save_hr_mail_for_debug
from laborman_agent.notify import Notifier, build_notification_command


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---- ロック ----


def test_second_lock_fails_while_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "agent.lock"
    with acquire_lock(lock_path):
        with pytest.raises(LockBusyError):
            with acquire_lock(lock_path):
                pass


def test_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "agent.lock"
    with acquire_lock(lock_path):
        pass
    with acquire_lock(lock_path):
        pass


# ---- 通知 ----


def test_notification_command_quotes_message() -> None:
    command = build_notification_command('2026-10-09: "解析"できませんでした\\')
    assert command[:2] == ["osascript", "-e"]
    assert command[2] == (
        'display notification "2026-10-09: \\"解析\\"できませんでした\\\\" with title "laborman-agent"'
    )


def test_notifier_runs_osascript_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: Any) -> None:
        calls.append(command)

    monkeypatch.setattr("sys.platform", "darwin")
    Notifier(enabled=True, runner=runner).notify("2026-10-09: 取込に失敗しました")
    Notifier(enabled=False, runner=runner).notify("通知しない")
    assert len(calls) == 1
    assert "2026-10-09: 取込に失敗しました" in calls[0][2]


def test_notifier_ignores_runner_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def runner(command: list[str], **_: Any) -> None:
        raise OSError("osascript not found")

    monkeypatch.setattr("sys.platform", "darwin")
    Notifier(enabled=True, runner=runner).notify("x")


# ---- ログ ----


def test_debug_mail_is_owner_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    saved = save_hr_mail_for_debug(log_dir, "[勤怠情報]2026/10/09", "本文", now=datetime(2026, 10, 13, 9, 20))
    assert saved.parent == log_dir / "hr_mail"
    assert mode(saved) == 0o600
    assert mode(log_dir) == 0o700
    assert mode(saved.parent) == 0o700
    assert saved.read_text(encoding="utf-8") == "件名: [勤怠情報]2026/10/09\n\n本文"


def test_ensure_private_dir_tightens_existing_dir(tmp_path: Path) -> None:
    path = tmp_path / "logs"
    path.mkdir(mode=0o755)
    path.chmod(0o755)
    ensure_private_dir(path)
    assert mode(path) == 0o700


def test_purge_removes_only_expired_files(tmp_path: Path) -> None:
    now = datetime(2026, 10, 13, 9, 20)
    old = save_hr_mail_for_debug(tmp_path, "old", "old", now=now - timedelta(days=15))
    recent = save_hr_mail_for_debug(tmp_path, "recent", "recent", now=now - timedelta(days=1))
    for path, age in [(old, 15), (recent, 1)]:
        timestamp = (now - timedelta(days=age)).timestamp()
        os.utime(path, (timestamp, timestamp))

    removed = purge_expired(tmp_path, retention_days=14, now=now)

    assert removed == [old]
    assert not old.exists()
    assert recent.exists()


def test_purge_ignores_missing_dir(tmp_path: Path) -> None:
    assert purge_expired(tmp_path / "missing", 14) == []

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
HR_MAIL_DIR = "hr_mail"
LOG_FILE = "agent.log"


def ensure_private_dir(path: Path) -> Path:
    """所有者のみアクセスできるディレクトリを作る（既存でも権限を 700 にそろえる）。"""
    path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
    path.chmod(PRIVATE_DIR_MODE)
    return path


def write_private_text(path: Path, text: str) -> Path:
    ensure_private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(text)
    path.chmod(PRIVATE_FILE_MODE)
    return path


def save_hr_mail_for_debug(log_dir: Path, subject: str, body: str | None, now: datetime | None = None) -> Path:
    """解析できなかった人事メールを調査用に保存する（DB には保存しない。保持期間で削除）。"""
    ensure_private_dir(log_dir)
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S-%f")
    content = f"件名: {subject}\n\n{body or ''}"
    return write_private_text(log_dir / HR_MAIL_DIR / f"{timestamp}.txt", content)


def purge_expired(log_dir: Path, retention_days: int, now: datetime | None = None) -> list[Path]:
    """保持期間を過ぎたファイルを削除し、削除したパスを返す。"""
    if not log_dir.exists():
        return []
    threshold = (now or datetime.now()) - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in log_dir.rglob("*"):
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime) < threshold:
            path.unlink()
            removed.append(path)
    return removed


def setup_file_logging(log_dir: Path) -> Path:
    """実行ログをファイルに出す。メール本文はログに出さないこと。"""
    ensure_private_dir(log_dir)
    log_path = log_dir / LOG_FILE
    if not log_path.exists():
        write_private_text(log_path, "")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("laborman_agent")
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    return log_path

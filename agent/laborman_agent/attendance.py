from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum

from laborman_agent.api_client import ApiError, AttendanceConflictError
from laborman_agent.config import AgentConfig
from laborman_agent.context import Context
from laborman_agent.exit_codes import ExitCode
from laborman_agent.logs import save_hr_mail_for_debug
from laborman_agent.owa.fetch import (
    HrMail,
    MailNotFoundError,
    NeedsLoginError,
    OwaPageError,
)
from laborman_agent.owa.parser import ParseError, ParserRules, parse_attendance

logger = logging.getLogger("laborman_agent")

MailFetcher = Callable[[AgentConfig, date, str, str], HrMail]
LEAVE_HINT = "休暇の日なら laborman の画面で出退勤を「休暇」として登録してください"


class AttendanceOutcome(Enum):
    IMPORTED = "imported"
    SKIPPED_MANUAL = "skipped_manual"  # 手入力（休暇を含む）の日
    NOT_FOUND = "not_found"
    NEEDS_LOGIN = "needs_login"
    FAILED = "failed"  # 設定不足・画面を認識できない・解析失敗・登録失敗


@dataclass(frozen=True)
class AttendanceResult:
    outcome: AttendanceOutcome
    message: str
    # 通知には載せず、標準エラーにだけ出す補足（解析失敗の理由と保存先）
    detail: str | None = None

    @property
    def exit_code(self) -> ExitCode:
        return {
            AttendanceOutcome.IMPORTED: ExitCode.OK,
            AttendanceOutcome.SKIPPED_MANUAL: ExitCode.OK,
            AttendanceOutcome.NOT_FOUND: ExitCode.RETRY_LATER,
            AttendanceOutcome.NEEDS_LOGIN: ExitCode.NEEDS_ATTENTION,
            AttendanceOutcome.FAILED: ExitCode.NEEDS_ATTENTION,
        }[self.outcome]

    @property
    def ok(self) -> bool:
        return self.exit_code == ExitCode.OK


def import_attendance(ctx: Context, target: date, fetcher: MailFetcher) -> AttendanceResult:
    """design D7 の流れ：手入力済みの確認 → OWA から取得 → 解析 → 登録。表示・通知は呼び出し側で行う。"""
    label = target.isoformat()
    report = ctx.client.get_report(target)
    if report.get("attendance_source") == "manual":
        kind = "休暇" if report.get("attendance_kind") == "leave" else "手入力"
        return AttendanceResult(
            AttendanceOutcome.SKIPPED_MANUAL,
            f"{label}: 出退勤は{kind}で登録済みのため、人事メールの取込をスキップしました",
        )

    settings = ctx.client.get_automation_settings()
    keyword = str(settings.get("hr_mail_subject_keyword") or "").strip()
    sender = str(settings.get("hr_mail_from") or "").strip()
    if not keyword:
        return AttendanceResult(
            AttendanceOutcome.FAILED,
            "人事メールの件名キーワードが未設定です。laborman の設定画面で入力してください",
        )

    try:
        mail = fetcher(ctx.config, target, keyword, sender)
    except NeedsLoginError:
        return AttendanceResult(
            AttendanceOutcome.NEEDS_LOGIN,
            f"{label}: Outlook on the web のサインインが必要です。laborman-agent login owa を実行してください",
        )
    except MailNotFoundError:
        return AttendanceResult(
            AttendanceOutcome.NOT_FOUND,
            f"{label}: 人事メールがまだ届いていません。後で再試行します。{LEAVE_HINT}",
        )
    except OwaPageError as exc:
        return AttendanceResult(AttendanceOutcome.FAILED, f"{label}: {exc}")

    try:
        record = parse_attendance(mail.subject, mail.body, target, ParserRules.from_mapping(ctx.config.owa.parser))
    except ParseError as exc:
        saved = save_hr_mail_for_debug(ctx.config.logs.dir, mail.subject, mail.body)
        logger.warning("解析失敗: %s（メールを %s に保存）", exc, saved)
        return AttendanceResult(
            AttendanceOutcome.FAILED,
            f"{label}: 人事メールを解析できませんでした",
            detail=f"理由: {exc}。調査用にメールを {saved} に保存しました",
        )

    try:
        ctx.client.put_attendance(target, record.start_at(), record.end_at())
    except AttendanceConflictError:
        return AttendanceResult(
            AttendanceOutcome.SKIPPED_MANUAL,
            f"{label}: 出退勤は手入力済みのため、人事メールの値（{record.start}–{record.end}）で上書きしませんでした",
        )
    except ApiError as exc:
        return AttendanceResult(AttendanceOutcome.FAILED, f"{label}: 出退勤を登録できませんでした（{exc.message}）")

    return AttendanceResult(
        AttendanceOutcome.IMPORTED, f"{label}: 人事メールから出退勤 {record.start}–{record.end} を登録しました"
    )

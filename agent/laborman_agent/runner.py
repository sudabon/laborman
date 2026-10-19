"""zac 登録の一連の実行（design D5、仕様書 §4.7）。

zac 保存成功日時の確認 → zac への到達性 → （出退勤が未取込なら）人事メールの取込 → ドラフトの検証
→ zac への入力 → モードに応じた保存 → 実行履歴の記録と通知。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from laborman_agent import __version__
from laborman_agent.attendance import AttendanceOutcome, MailFetcher, import_attendance
from laborman_agent.context import Context
from laborman_agent.exit_codes import ExitCode
from laborman_agent.logs import PRIVATE_FILE_MODE, ensure_private_dir
from laborman_agent.owa.fetch import fetch_hr_mail
from laborman_agent.zac.credentials import read_password
from laborman_agent.zac.report_page import ZacOptionNotFoundError, ZacPageError
from laborman_agent.zac import (
    ZacNotImplementedError,
    ZacReportPage,
    ZacSessionFactory,
    check_zac_reachable,
    open_zac_session,
    SignInResult,
    sign_in_failure_message,
    sign_in_with_keychain,
)

logger = logging.getLogger("laborman_agent")

# assist で利用者の保存を待つ時間・auto で保存完了の表示を待つ時間
ASSIST_WAIT_SECONDS = 15 * 60
SAVE_WAIT_SECONDS = 60
SCREENSHOT_DIR = "screenshots"

Reachability = Callable[[str], bool]
PasswordReader = Callable[[str, str], str | None]


@dataclass(frozen=True)
class RunOptions:
    mode: str | None = None  # 省略時は laborman の設定の実行モード
    headed: bool = False
    force: bool = False
    # register は人事メールの取込を行わない
    import_attendance: bool = True
    # 画面からの依頼（requested → claim 済み）の実行履歴 ID。指定時は新しい履歴を作らない
    run_id: str | None = None
    # 画面からの依頼は利用者が結果を待っているため、再試行状態も常に通知する
    interactive: bool = False


def parse_hhmm(value: str) -> time:
    hours, minutes = (int(part) for part in value.split(":"))
    return time(hours, minutes)


def screenshot_path(ctx: Context, target: date, run_id: str) -> Path:
    directory = ensure_private_dir(ctx.config.logs.dir / SCREENSHOT_DIR)
    return directory / f"{target.isoformat()}_{run_id}.png"


def error_messages(draft: dict[str, Any]) -> list[str]:
    return [str(issue["message"]) for issue in draft.get("issues", []) if issue.get("severity") == "error"]


def has_issue(draft: dict[str, Any], code: str) -> bool:
    return any(issue.get("code") == code for issue in draft.get("issues", []))


class Runner:
    def __init__(
        self,
        ctx: Context,
        *,
        fetcher: MailFetcher = fetch_hr_mail,
        zac_session: ZacSessionFactory = open_zac_session,
        reachable: Reachability = check_zac_reachable,
        now: Callable[[], datetime] = datetime.now,
        password_reader: PasswordReader = read_password,
    ) -> None:
        self.ctx = ctx
        self.fetcher = fetcher
        self.zac_session = zac_session
        self.reachable = reachable
        self.now = now
        self.password_reader = password_reader
        self._interactive = False

    def run(self, target: date, options: RunOptions = RunOptions()) -> ExitCode:
        ctx = self.ctx
        label = target.isoformat()
        draft = ctx.client.get_zac_draft(target)
        if draft.get("zac_registered_at") and not options.force:
            message = f"{label}: zac 登録済みのためスキップしました"
            if options.run_id:
                ctx.client.update_zac_run(options.run_id, status="already_registered_in_zac", message=message)
            ctx.say(message)
            return ExitCode.OK

        mode = options.mode or str(ctx.client.get_automation_settings().get("zac_submit_mode") or "dry_run")
        run_id = options.run_id or str(ctx.client.create_zac_run(target, mode, __version__)["id"])
        try:
            return self._run_recorded(target, draft, mode, run_id, options)
        except Exception:
            # スタックトレースはログにのみ出す（画面の内容やメール本文は記録しない）
            logger.exception("zac 登録の想定外のエラー")
            message = f"{label}: zac 登録で想定外のエラーが発生しました。ログを確認してください"
            ctx.client.update_zac_run(run_id, status="failed", message=message)
            ctx.warn(message)
            return ExitCode.ERROR

    # ---- 結果の記録と通知 ----

    def _record(
        self,
        run_id: str,
        status: str,
        message: str,
        code: ExitCode,
        *,
        notify: bool = True,
        retry: bool = False,
        **fields: Any,
    ) -> ExitCode:
        self.ctx.client.update_zac_run(run_id, status=status, message=message, **fields)
        if code == ExitCode.OK:
            self.ctx.say(message)
            if notify:
                self.ctx.notifier.notify(message)
        else:
            self.ctx.warn(message, notify=notify and (not retry or self._notify_retry))
        return code

    @property
    def _notify_retry(self) -> bool:
        """再試行状態は、その日の最終回（設定の時刻以降）の起動か、画面からの依頼のときだけ通知する。"""
        if self._interactive:
            return True
        return self.now().time() >= parse_hhmm(self.ctx.config.schedule.notify_retry_after)

    # ---- 本体 ----

    def _run_recorded(
        self, target: date, draft: dict[str, Any], mode: str, run_id: str, options: RunOptions
    ) -> ExitCode:
        ctx = self.ctx
        label = target.isoformat()
        self._interactive = options.interactive
        zac = ctx.config.zac

        if not zac.configured:
            return self._record(
                run_id,
                "failed",
                f"{label}: zac の URL が未設定です。config.toml の [zac] を設定してください",
                ExitCode.NEEDS_ATTENTION,
            )
        if not self.reachable(zac.probe_url):
            return self._record(
                run_id,
                "vpn_unreachable",
                f"{label}: zac に接続できません（VPN 未接続）。後で再試行します",
                ExitCode.RETRY_LATER,
                retry=True,
            )

        if options.import_attendance and has_issue(draft, "ATTENDANCE_MISSING"):
            result = import_attendance(ctx, target, self.fetcher)
            if result.detail:
                print(result.detail, file=ctx.err)
            if result.outcome == AttendanceOutcome.NOT_FOUND:
                return self._record(run_id, "hr_mail_not_found", result.message, ExitCode.RETRY_LATER, retry=True)
            if result.outcome == AttendanceOutcome.NEEDS_LOGIN:
                return self._record(run_id, "needs_login", result.message, ExitCode.NEEDS_ATTENTION)
            if result.outcome == AttendanceOutcome.FAILED:
                return self._record(run_id, "failed", result.message, ExitCode.NEEDS_ATTENTION)
            ctx.say(result.message)
            draft = ctx.client.get_zac_draft(target)

        if not draft.get("registrable"):
            errors = error_messages(draft)
            return self._record(
                run_id,
                "validation_failed",
                f"{label}: zac 登録を中止しました（{'・'.join(errors)}）",
                ExitCode.NEEDS_ATTENTION,
                entries=draft.get("entries"),
            )

        effective = mode
        downgraded = mode == "auto" and not draft.get("auto_allowed")
        if downgraded:
            effective = "dry_run"
            ctx.warn(f"{label}: 警告があるため auto から dry_run に降格し、保存しません")

        try:
            with self.zac_session(ctx.config, options.headed or effective == "assist") as page:
                return self._operate(page, target, draft, effective, run_id, downgraded)
        except ZacNotImplementedError as exc:
            return self._record(run_id, "failed", f"{label}: {exc}", ExitCode.NEEDS_ATTENTION)
        except (ZacOptionNotFoundError, ZacPageError) as exc:
            # 入力を中止する（保存はしていない）。一致しなかった項目・画面の問題を記録する
            return self._record(
                run_id,
                "failed",
                f"{label}: zac への入力を中止しました（{exc}）。保存していません",
                ExitCode.NEEDS_ATTENTION,
                entries=draft.get("entries"),
            )

    def _operate(
        self,
        page: ZacReportPage,
        target: date,
        draft: dict[str, Any],
        mode: str,
        run_id: str,
        downgraded: bool,
    ) -> ExitCode:
        label = target.isoformat()
        entries = draft.get("entries")
        page.open(target)
        if page.is_login_page():
            result = sign_in_with_keychain(page, self.ctx.config, target, self.password_reader)
            if result != SignInResult.SIGNED_IN:
                logger.warning("zac にサインインできませんでした（%s）", result.value)
                return self._record(
                    run_id,
                    "needs_login",
                    f"{label}: {sign_in_failure_message(self.ctx.config, result)}",
                    ExitCode.NEEDS_ATTENTION,
                )
        if page.has_existing_entries():
            return self._record(
                run_id,
                "already_registered_in_zac",
                f"{label}: zac にすでに入力があるため、上書きせずに終了しました",
                ExitCode.NEEDS_ATTENTION,
            )

        try:
            page.fill(draft)
            page.fill_breaks(list(draft.get("breaks") or []))
        except (ZacOptionNotFoundError, ZacPageError) as exc:
            # 入力を中止する（保存はしていない）。原因を調べられるよう画面と選択肢を残す
            shot = self._screenshot(page, target, run_id)
            if isinstance(exc, ZacOptionNotFoundError):
                logger.warning("%s: %s の選択肢に出ていたもの: %s", label, exc.field_label, exc.seen)
            return self._record(
                run_id,
                "failed",
                f"{label}: zac への入力を中止しました（{exc}）。保存していません",
                ExitCode.NEEDS_ATTENTION,
                entries=entries,
                screenshot_path=str(shot),
            )
        shot = self._screenshot(page, target, run_id)

        if mode == "dry_run":
            suffix = "（auto から降格）" if downgraded else ""
            return self._record(
                run_id,
                "dry_run_done",
                f"{label}: zac に入力しました（保存していません）{suffix}",
                ExitCode.OK,
                notify=downgraded or self._interactive,
                entries=entries,
                screenshot_path=str(shot),
            )
        if mode == "assist":
            self.ctx.notifier.notify(f"{label}: zac に入力しました。内容を確認して保存してください")
            if page.wait_saved(ASSIST_WAIT_SECONDS) and not page.has_error():
                return self._record(
                    run_id,
                    "succeeded",
                    f"{label}: zac の保存を確認しました",
                    ExitCode.OK,
                    entries=entries,
                    screenshot_path=str(shot),
                )
            return self._record(
                run_id,
                "awaiting_user",
                f"{label}: zac の保存を確認できないまま時間切れになりました",
                ExitCode.NEEDS_ATTENTION,
                entries=entries,
                screenshot_path=str(shot),
            )

        page.click_save()
        if page.wait_saved(SAVE_WAIT_SECONDS) and not page.has_error():
            return self._record(
                run_id,
                "succeeded",
                f"{label}: zac に保存しました",
                ExitCode.OK,
                entries=entries,
                screenshot_path=str(shot),
            )
        shot = self._screenshot(page, target, run_id)
        return self._record(
            run_id,
            "failed",
            f"{label}: zac の保存完了を確認できませんでした。スクリーンショットを確認してください",
            ExitCode.NEEDS_ATTENTION,
            entries=entries,
            screenshot_path=str(shot),
        )

    def _screenshot(self, page: ZacReportPage, target: date, run_id: str) -> Path:
        path = screenshot_path(self.ctx, target, run_id)
        page.screenshot(path)
        if path.exists():
            path.chmod(PRIVATE_FILE_MODE)
        return path

from __future__ import annotations

import argparse
import logging
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Protocol, TextIO

from laborman_agent import __version__
from laborman_agent.api_client import (
    ApiError,
    ApiUnavailableError,
    ConflictError,
    LabormanClient,
)
from laborman_agent.business_days import parse_date_arg, resolve_target_date
from laborman_agent.config import AgentConfig, ConfigError, load_config, permission_warning
from laborman_agent.attendance import MailFetcher, import_attendance
from laborman_agent.context import Context
from laborman_agent.exit_codes import ExitCode
from laborman_agent.lock import LockBusyError, acquire_lock
from laborman_agent.logs import purge_expired, setup_file_logging
from laborman_agent.notify import Notifier
from laborman_agent.owa.fetch import (
    fetch_hr_mail,
    login_owa,
    owa_profile_dir,
)
from laborman_agent.runner import Runner, RunOptions
from laborman_agent.zac import (
    SignInResult,
    check_zac_reachable,
    login_zac,
    sign_in_failure_message,
    sign_in_with_keychain,
    zac_profile_dir,
)
from laborman_agent.zac.credentials import has_password, read_password, registration_hint

logger = logging.getLogger("laborman_agent")


# ---- fetch-attendance ----


def fetch_attendance(ctx: Context, target: date, fetcher: MailFetcher = fetch_hr_mail) -> ExitCode:
    result = import_attendance(ctx, target, fetcher)
    if result.ok:
        ctx.say(result.message)
    else:
        ctx.warn(result.message)
    if result.detail:
        print(result.detail, file=ctx.err)
    return result.exit_code


def run_fetch_attendance(
    ctx: Context, date_arg: str | None, fetcher: MailFetcher = fetch_hr_mail, today: date | None = None
) -> ExitCode:
    try:
        with acquire_lock(ctx.config.lock_path):
            purge_expired(ctx.config.logs.dir, ctx.config.logs.retention_days)
            target = resolve_target_date(date_arg, today)
            return fetch_attendance(ctx, target, fetcher)
    except LockBusyError:
        ctx.say("別の laborman-agent が実行中のため、何もせずに終了します")
        return ExitCode.OK


# ---- run / register / process-requests ----

class SupportsRun(Protocol):
    def run(self, target: date, options: RunOptions = ...) -> ExitCode: ...


RunnerFactory = Callable[[Context], SupportsRun]


def run_zac(
    ctx: Context,
    date_arg: str | None,
    options: RunOptions,
    runner_factory: RunnerFactory = Runner,
    today: date | None = None,
) -> ExitCode:
    """`run`（人事メールの取込から）と `register`（zac 以降だけ）。"""
    try:
        with acquire_lock(ctx.config.lock_path):
            purge_expired(ctx.config.logs.dir, ctx.config.logs.retention_days)
            target = resolve_target_date(date_arg, today)
            return runner_factory(ctx).run(target, options)
    except LockBusyError:
        ctx.say("別の laborman-agent が実行中のため、何もせずに終了します")
        return ExitCode.OK


def process_requests(ctx: Context, runner_factory: RunnerFactory = Runner) -> ExitCode:
    """画面の「この日を zac に登録」で記録された依頼を古い順に実行する（launchd から 1 分間隔で起動）。"""
    try:
        with acquire_lock(ctx.config.lock_path):
            requests = ctx.client.list_zac_runs(status="requested", oldest_first=True)
            if not requests:
                return ExitCode.OK
            purge_expired(ctx.config.logs.dir, ctx.config.logs.retention_days)
            runner = runner_factory(ctx)
            codes: list[ExitCode] = []
            for request in requests:
                try:
                    claimed = ctx.client.claim_zac_run(str(request["id"]))
                except ConflictError:
                    # 取り消された・ほかの起動が取得した依頼は実行しない
                    continue
                target = date.fromisoformat(str(claimed["work_date"]))
                options = RunOptions(mode=str(claimed["mode"]), run_id=str(claimed["id"]), interactive=True)
                codes.append(runner.run(target, options))
            return max(codes, default=ExitCode.OK)
    except LockBusyError:
        # 実行中の処理が終われば、次の起動で依頼を拾う
        return ExitCode.OK


# ---- sync-zac ----

MasterReaderFactory = Callable[[AgentConfig], AbstractContextManager[Any]]


@contextmanager
def open_master_reader(config: AgentConfig) -> Iterator[Any]:
    from laborman_agent.zac.report_page import ZacMasterReader, zac_browser_page

    with zac_browser_page(config, headed=False) as page:
        yield ZacMasterReader(page, config)


def sync_zac(
    ctx: Context,
    date_arg: str | None,
    reader_factory: MasterReaderFactory = open_master_reader,
    reachable: Callable[[str], bool] = check_zac_reachable,
    password_reader: Callable[[str, str], str | None] = read_password,
    today: date | None = None,
) -> ExitCode:
    """zac の作業登録の画面から選択肢を読み取り、laborman のマスタに取り込む（zac には何も保存しない）。"""
    from laborman_agent.zac.report_page import ZacOptionNotFoundError, ZacPageError

    zac = ctx.config.zac
    if not zac.configured:
        ctx.warn("zac の URL が未設定です。config.toml の [zac] を設定してください")
        return ExitCode.NEEDS_ATTENTION
    if not reachable(zac.probe_url):
        ctx.warn("zac に接続できません（VPN 未接続）", notify=False)
        return ExitCode.RETRY_LATER
    # 作業登録を開ける未確定の日（既定は今日）で読み取る
    target = parse_date_arg(date_arg) if date_arg else (today or date.today())
    try:
        with acquire_lock(ctx.config.lock_path), reader_factory(ctx.config) as reader:
            reader.open(target)
            if reader.is_login_page():
                sign_in = sign_in_with_keychain(reader, ctx.config, target, password_reader)
                if sign_in != SignInResult.SIGNED_IN:
                    ctx.warn(sign_in_failure_message(ctx.config, sign_in))
                    return ExitCode.NEEDS_ATTENTION
            masters = reader.read_masters()
    except LockBusyError:
        ctx.say("別の laborman-agent が実行中のため、何もせずに終了します")
        return ExitCode.OK
    except (ZacPageError, ZacOptionNotFoundError) as exc:
        ctx.warn(f"zac の選択肢を読み取れませんでした（{exc}）")
        return ExitCode.NEEDS_ATTENTION

    # zac の候補には過去月の案件が残るので、読み取りに使った日の月より前の案件は取り込まない
    payload = {**masters.as_import_payload(), "as_of_month": target.strftime("%Y-%m")}
    result = ctx.client.import_zac_masters(payload)
    created, updated = result["created"], result["updated"]
    ctx.say(
        f"zac の選択肢を取り込みました：作業内容 {len(masters.work_kinds)} 件・案件 {len(masters.projects)} 件"
        f"（追加 案件 {created['jobs']}・売上項目 {created['sales_items']}・作業内容 {created['work_kinds']}、"
        f"更新 案件 {updated['jobs']}・売上項目 {updated['sales_items']}）"
    )
    if result.get("skipped_jobs"):
        ctx.say(f"過去月の案件 {len(result['skipped_jobs'])} 件は取り込みませんでした：" + "、".join(result["skipped_jobs"]))
    if result["missing_jobs"]:
        ctx.say(
            "zac の候補に現れなかった有効なジョブ（無効化はしていません）：" + "、".join(result["missing_jobs"])
        )
    return ExitCode.OK


# ---- doctor ----


def _check(out: TextIO, ok: bool, label: str, detail: str) -> bool:
    print(f"[{'OK' if ok else 'NG'}] {label}: {detail}", file=out)
    return ok


def check_browser(config: AgentConfig) -> tuple[bool, str]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    channel = config.browser.channel or None
    name = channel or "Playwright Chromium"
    try:
        with sync_playwright() as playwright:
            playwright.chromium.launch(channel=channel, headless=True).close()
    except PlaywrightError as exc:
        hint = "uv run playwright install chromium" if channel is None else f"{channel} をインストールしてください"
        return False, f"{name} を起動できません（{hint}）: {str(exc).splitlines()[0]}"
    return True, f"{name} を起動できます"


def doctor(
    ctx: Context,
    browser_check: Callable[[AgentConfig], tuple[bool, str]] = check_browser,
    reachable: Callable[[str], bool] = check_zac_reachable,
    password_check: Callable[[str, str], bool] = has_password,
) -> ExitCode:
    config = ctx.config
    results: list[bool] = []

    if config.exists:
        warning = permission_warning(config.path)
        results.append(_check(ctx.out, warning is None, "設定ファイル", warning or f"{config.path}（権限 600）"))
    else:
        results.append(_check(ctx.out, False, "設定ファイル", f"{config.path} がありません（SETUP_GUIDE.md を参照）"))

    try:
        ctx.client.health()
        results.append(_check(ctx.out, True, "laborman API", config.api_base_url))
        settings = ctx.client.get_automation_settings()
        keyword = str(settings.get("hr_mail_subject_keyword") or "")
        results.append(
            _check(
                ctx.out,
                bool(keyword),
                "人事メールの条件",
                f"件名キーワード {keyword}" if keyword else "件名キーワードが未設定です（laborman の設定画面）",
            )
        )
    except (ApiUnavailableError, ApiError) as exc:
        results.append(_check(ctx.out, False, "laborman API", str(exc)))

    profile = owa_profile_dir(config)
    if profile.is_dir():
        mode = stat.S_IMODE(profile.stat().st_mode)
        detail = f"{profile}（権限 {mode:o}）"
        if mode & 0o077:
            detail += f"。chmod 700 {profile} を実行してください"
        results.append(_check(ctx.out, not mode & 0o077, "OWA プロファイル", detail))
    else:
        results.append(
            _check(ctx.out, False, "OWA プロファイル", f"{profile} がありません。laborman-agent login owa を実行してください")
        )

    ok, detail = browser_check(config)
    results.append(_check(ctx.out, ok, "ブラウザ", detail))

    results.extend(check_zac(ctx, reachable, password_check))

    return ExitCode.OK if all(results) else ExitCode.NEEDS_ATTENTION


def check_zac(
    ctx: Context, reachable: Callable[[str], bool], password_check: Callable[[str, str], bool]
) -> list[bool]:
    zac = ctx.config.zac
    if not zac.configured:
        return [_check(ctx.out, False, "zac", "URL が未設定です（config.toml の [zac] base_url）")]
    results = [
        _check(
            ctx.out,
            reachable(zac.probe_url),
            "zac への到達性",
            zac.probe_url if reachable(zac.probe_url) else f"{zac.probe_url} に接続できません（VPN を確認してください）",
        )
    ]
    profile = zac_profile_dir(ctx.config)
    if profile.is_dir():
        mode = stat.S_IMODE(profile.stat().st_mode)
        results.append(_check(ctx.out, not mode & 0o077, "zac プロファイル", f"{profile}（権限 {mode:o}）"))
    else:
        results.append(
            _check(ctx.out, False, "zac プロファイル", f"{profile} がありません。laborman-agent login zac を実行してください")
        )
    # パスワードの値は表示しない（登録の有無だけ）
    if not zac.login_id:
        results.append(_check(ctx.out, False, "zac のパスワード", "config.toml の [zac] login_id が未設定です"))
    elif password_check(zac.keychain_service, zac.login_id):
        results.append(
            _check(ctx.out, True, "zac のパスワード", f"キーチェーンに登録済み（{zac.keychain_service} / {zac.login_id}）")
        )
    else:
        results.append(
            _check(
                ctx.out,
                False,
                "zac のパスワード",
                f"キーチェーンに未登録です。{registration_hint(zac.keychain_service, zac.login_id)} で登録してください",
            )
        )
    return results


# ---- login ----


def login(ctx: Context, target: str) -> ExitCode:
    if target == "zac":
        if not ctx.config.zac.configured:
            print("zac の URL が未設定です（config.toml の [zac] base_url）", file=ctx.err)
            return ExitCode.NEEDS_ATTENTION
        print("ブラウザで zac にサインインし、業務報告の画面が表示されたらブラウザを閉じてください。", file=ctx.out)
        profile = login_zac(ctx.config)
    else:
        print("ブラウザで Outlook on the web にサインインし、メールが表示されたらブラウザを閉じてください。", file=ctx.out)
        profile = login_owa(ctx.config)
    ctx.say(f"セッションを {profile} に保存しました")
    return ExitCode.OK


# ---- entry point ----


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="laborman-agent",
        description="laborman のホスト側 CLI（人事メールの出退勤の取込と zac 業務報告の入力）",
        epilog="終了コード: 0 完了・スキップ / 1 想定外のエラー / 2 後で再試行 / 3 人の対応が必要",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="設定ファイル（既定 ~/.config/laborman-agent/config.toml）")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    login_parser = commands.add_parser("login", help="画面付きブラウザで手動サインインし、セッションを保存する")
    login_parser.add_argument("target", choices=["owa", "zac"], help="サインイン先")

    fetch_parser = commands.add_parser("fetch-attendance", help="人事メールから出退勤を取り込む")
    fetch_parser.add_argument("--date", help="対象日 YYYY-MM-DD（既定は前営業日）")

    for name, help_text in [
        ("run", "人事メールの取込から zac への入力・保存までを行う"),
        ("register", "人事メールを取り込まずに zac への入力・保存だけを行う"),
    ]:
        run_parser = commands.add_parser(name, help=help_text)
        run_parser.add_argument("--date", help="対象日 YYYY-MM-DD（既定は前営業日）")
        run_parser.add_argument(
            "--mode", choices=["dry_run", "assist", "auto"], help="実行モード（既定は laborman の設定）"
        )
        run_parser.add_argument("--headed", action="store_true", help="画面付きのブラウザで実行する")
        run_parser.add_argument("--force", action="store_true", help="zac 登録済みの日も実行する")

    commands.add_parser("process-requests", help="画面からの zac 登録の依頼を実行する（launchd から 1 分間隔）")

    sync_parser = commands.add_parser(
        "sync-zac", help="zac の作業内容・案件・売上項目の選択肢を laborman に取り込む（zac には保存しない）"
    )
    sync_parser.add_argument("--date", help="読み取りに使う未確定の日 YYYY-MM-DD（既定は今日）")
    commands.add_parser("doctor", help="API・設定・プロファイル・ブラウザ・zac への到達性を診断する")
    return parser


def main(argv: list[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in ("fetch-attendance", "run", "register", "sync-zac") and args.date:
        try:
            parse_date_arg(args.date)
        except ValueError as exc:
            parser.error(str(exc))

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=err)
        return ExitCode.NEEDS_ATTENTION

    notifier = Notifier(enabled=config.notify.macos)
    try:
        setup_file_logging(config.logs.dir)
    except OSError as exc:
        print(f"ログディレクトリを準備できません: {exc}", file=err)
    with LabormanClient(config.api_base_url) as client:
        ctx = Context(config=config, client=client, notifier=notifier, out=out, err=err)
        for warning in config.warnings:
            ctx.warn(warning, notify=args.command != "doctor")
        try:
            if args.command == "fetch-attendance":
                return run_fetch_attendance(ctx, args.date)
            if args.command in ("run", "register"):
                options = RunOptions(
                    mode=args.mode,
                    headed=args.headed,
                    force=args.force,
                    import_attendance=args.command == "run",
                )
                return run_zac(ctx, args.date, options)
            if args.command == "process-requests":
                return process_requests(ctx)
            if args.command == "sync-zac":
                return sync_zac(ctx, args.date)
            if args.command == "doctor":
                return doctor(ctx)
            return login(ctx, args.target)
        except ApiUnavailableError as exc:
            print(exc, file=err)
            logger.error("%s", exc)
            return ExitCode.ERROR
        except Exception:
            # スタックトレースはログにのみ出す（メール本文は例外に含めない）
            logger.exception("想定外のエラー")
            print("想定外のエラーが発生しました。詳細はログを確認してください", file=err)
            return ExitCode.ERROR


if __name__ == "__main__":
    sys.exit(main())

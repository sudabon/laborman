from __future__ import annotations

import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/.config/laborman-agent/config.toml")
DEFAULT_API_BASE_URL = "http://127.0.0.1:8888"
DEFAULT_PROFILE_DIR = Path("~/Library/Application Support/laborman-agent/profiles")
DEFAULT_STATE_DIR = Path("~/Library/Application Support/laborman-agent")
DEFAULT_LOG_DIR = Path("~/Library/Logs/laborman-agent")
DEFAULT_RETENTION_DAYS = 14

DEFAULT_OWA_URL = "https://outlook.office.com/mail/"
# target_date は YYYY/MM/DD。from_clause は差出人が設定されていれば 'from:"…" '、なければ空
DEFAULT_SEARCH_QUERY = '{from_clause}subject:"{hr_mail_subject_keyword}{target_date}"'

# OWA の画面のセレクタ。画面の変更にコード修正なしで追従できるよう [owa.selectors] で上書きする
DEFAULT_OWA_SELECTORS: dict[str, str] = {
    "search_box": "#topSearchInput",
    # 検索結果の 1 件（メール一覧の行）
    "search_result": "[role=option]",
    # 検索結果の行の中の件名。空なら行全体のテキストを使う
    "result_subject": "",
    "message_body": "[aria-label='メッセージ本文'], [aria-label='Message body']",
    # これが見えたらサインインが必要
    "login_form": "input[name='loginfmt']",
}

# 人事メールの解析規則。NFKC 正規化後の文字列に適用する（2026-10-13 受信の実メールで確定）
DEFAULT_PARSER_PATTERNS: dict[str, str] = {
    "subject_pattern": (
        r"\[勤怠情報\](?P<date>\d{4}/\d{1,2}/\d{1,2})"
        r":開始(?P<start>\d{1,2}:\d{2})/終了(?P<end>\d{1,2}:\d{2})"
    ),
    "body_date_pattern": r"対象日\s*(?P<date>\d{4}/\d{1,2}/\d{1,2})",
    "body_start_pattern": r"開始時間\s*(?P<start>\d{1,2}:\d{2})",
    "body_end_pattern": r"終了時間\s*(?P<end>\d{1,2}:\d{2})",
}


# zac の画面のセレクタ（2026-10-14 に Claude in Chrome で確認した画面。design D12）。
# Playwright のセレクタで、[zac.selectors] で上書きできる。ダイアログ内の要素はダイアログを起点に探す
DEFAULT_ZAC_SELECTORS: dict[str, str] = {
    # サインイン画面（/User/user_logon.asp）
    "login_form": "#password",
    "login_id_input": "#username",
    "login_password_input": "#password",
    "login_submit": "form:has(#password) button[type=submit]",
    # 勤怠欄
    "attendance_start": "zac-time-duration-input[formcontrolname=TimeIn] input",
    "attendance_end": "zac-time-duration-input[formcontrolname=TimeOut] input",
    "break_normal": "zac-time-duration-input[formcontrolname=TimeBreak] input",
    "break_late": "zac-time-duration-input[formcontrolname=TimeBreak3] input",
    "break_overnight": "zac-time-duration-input[formcontrolname=TimeBreak4] input",
    # 既存入力・確定済み
    "existing_rows": "tr.zac-row.cdk-row.data-row",
    "confirmed_indicator": "text=日報確定済",
    # 作業登録のダイアログ
    "register_open": "button:has-text('作業登録')",
    "dialog": ".cdk-overlay-pane:has([formcontrolname=TimeRequired])",
    "row_work_kind": "zac-entity-dropdown[formcontrolname=IdSagyouNaiyou]",
    "row_project_input": "zac-entity-select-v2[formcontrolname=IdProject] input",
    "row_sales_item": "zac-entity-dropdown-v2[formcontrolname=IdProjectSales]",
    "row_minutes": "zac-time-duration-input[formcontrolname=TimeRequired] input",
    "row_description": "zac-textarea[formcontrolname=Memo] textarea",
    # zac のボタンは文字の前後に空白などを含むため、:text-is ではなく種類（class）と部分一致で特定する
    "row_register": "button.success:has-text('登録')",
    "row_cancel": "button.basic:has-text('キャンセル')",
    "option": ".cdk-overlay-pane zac-option",
    # 保存（「確定」は押さない）
    # 画面に「保存」が 2 つ（DOM 上）あるため、見えているものを押す
    "save_button": "button.basic:has-text('保存'):visible",
    # 保存完了・エラーの表示。zac は保存しても画面にメッセージを出さない（2026-10-14 に確認）ため、
    # 保存完了は保存の通信（DEFAULT_ZAC_SAVE_RESPONSE_PATTERN）の成功で判定する。表示でも判定したいときだけ設定する
    "saved_indicator": "",
    "error_message": "",
}
# 「保存」で送られる通信の URL（2026-10-14 に確認：POST …/b/api/v2/daily_report/daily_reports/{date}/save → 200）
DEFAULT_ZAC_SAVE_RESPONSE_PATTERN = "/api/v2/daily_report/daily_reports/{date}/save"
# 案件を選んだあとに売上項目の選択肢を読み込む通信（2026-10-14 に確認）。応答を待ってから売上項目を読む
DEFAULT_ZAC_SALES_RESPONSE_PATTERN = "/api/v2/reference/daily_report_project_sales"
DEFAULT_ZAC_REPORT_URL_TEMPLATE = "{base_url}/b/daily_report/{date}"
# sync-zac で案件の候補を出すために選ぶ作業内容
DEFAULT_SYNC_WORK_KIND = "プロジェクト作業"
DEFAULT_NOTIFY_RETRY_AFTER = "13:00"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class BrowserConfig:
    profile_dir: Path = DEFAULT_PROFILE_DIR.expanduser()
    # 条件付きアクセスで同梱 Chromium が弾かれる場合に "chrome" / "msedge" を使う。空なら同梱 Chromium
    channel: str = "chrome"
    headless: bool = True
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class OwaConfig:
    url: str = DEFAULT_OWA_URL
    search_query: str = DEFAULT_SEARCH_QUERY
    selectors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_OWA_SELECTORS))
    parser: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PARSER_PATTERNS))


DEFAULT_KEYCHAIN_SERVICE = "laborman-agent.zac"


@dataclass(frozen=True)
class ZacConfig:
    base_url: str = ""
    # zac のログイン ID。パスワードは macOS キーチェーン（keychain_service）にだけ置く
    login_id: str = ""
    keychain_service: str = DEFAULT_KEYCHAIN_SERVICE
    # VPN 接続の確認に使う URL（空なら base_url）
    reachability_url: str = ""
    # 業務報告画面の URL。{base_url}・{date}（YYYY-MM-DD）・{date_slash}（YYYY/MM/DD）を埋め込む
    report_url_template: str = DEFAULT_ZAC_REPORT_URL_TEMPLATE
    selectors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ZAC_SELECTORS))
    sync_work_kind: str = DEFAULT_SYNC_WORK_KIND
    # 保存の通信の URL に含まれる文字列（{date} は YYYY-MM-DD）
    save_response_pattern: str = DEFAULT_ZAC_SAVE_RESPONSE_PATTERN
    sales_response_pattern: str = DEFAULT_ZAC_SALES_RESPONSE_PATTERN

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def probe_url(self) -> str:
        return self.reachability_url or self.base_url


@dataclass(frozen=True)
class ScheduleConfig:
    # 再試行状態（VPN 未接続・メール未着）の通知はこの時刻以降の起動だけで行う（launchd の最終回）
    notify_retry_after: str = DEFAULT_NOTIFY_RETRY_AFTER


@dataclass(frozen=True)
class NotifyConfig:
    macos: bool = True


@dataclass(frozen=True)
class LogsConfig:
    dir: Path = DEFAULT_LOG_DIR.expanduser()
    retention_days: int = DEFAULT_RETENTION_DAYS


@dataclass(frozen=True)
class AgentConfig:
    path: Path
    exists: bool
    api_base_url: str = DEFAULT_API_BASE_URL
    state_dir: Path = DEFAULT_STATE_DIR.expanduser()
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    owa: OwaConfig = field(default_factory=OwaConfig)
    zac: ZacConfig = field(default_factory=ZacConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    logs: LogsConfig = field(default_factory=LogsConfig)
    warnings: tuple[str, ...] = ()

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "agent.lock"


def permission_warning(path: Path) -> str | None:
    """所有者以外が読み書きできる設定ファイルなら警告文を返す。"""
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return f"設定ファイル {path} の権限が {mode:o} です。chmod 600 {path} を実行してください"
    return None


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] はテーブルで指定してください")
    return value


def _string_map(
    data: dict[str, Any], name: str, defaults: dict[str, str], parent: str = "owa"
) -> dict[str, str]:
    merged = dict(defaults)
    for key, value in _section(data, name).items():
        if not isinstance(value, str):
            raise ConfigError(f"[{parent}.{name}] の {key} は文字列で指定してください")
        merged[key] = value
    return merged


def _path(value: Any, default: Path) -> Path:
    if value is None:
        return default
    return Path(str(value)).expanduser()


def load_config(path: Path | None = None) -> AgentConfig:
    """設定ファイルを読み込む。ファイルがなければ既定値を使う。"""
    config_path = (path or DEFAULT_CONFIG_PATH).expanduser()
    if not config_path.exists():
        return AgentConfig(path=config_path, exists=False)

    warnings: list[str] = []
    warning = permission_warning(config_path)
    if warning:
        warnings.append(warning)

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"設定ファイル {config_path} を読み込めません: {exc}") from exc

    laborman = _section(data, "laborman")
    browser = _section(data, "browser")
    owa = _section(data, "owa")
    zac = _section(data, "zac")
    schedule = _section(data, "schedule")
    notify = _section(data, "notify")
    logs = _section(data, "logs")
    defaults_browser = BrowserConfig()
    defaults_logs = LogsConfig()

    return AgentConfig(
        path=config_path,
        exists=True,
        api_base_url=str(laborman.get("api_base_url", DEFAULT_API_BASE_URL)).rstrip("/"),
        state_dir=_path(laborman.get("state_dir"), DEFAULT_STATE_DIR.expanduser()),
        browser=BrowserConfig(
            profile_dir=_path(browser.get("profile_dir"), defaults_browser.profile_dir),
            channel=str(browser.get("channel", defaults_browser.channel)),
            headless=bool(browser.get("headless", defaults_browser.headless)),
            timeout_seconds=float(browser.get("timeout_seconds", defaults_browser.timeout_seconds)),
        ),
        owa=OwaConfig(
            url=str(owa.get("url", DEFAULT_OWA_URL)),
            search_query=str(owa.get("search_query", DEFAULT_SEARCH_QUERY)),
            selectors=_string_map(owa, "selectors", DEFAULT_OWA_SELECTORS),
            parser=_string_map(owa, "parser", DEFAULT_PARSER_PATTERNS),
        ),
        zac=ZacConfig(
            base_url=str(zac.get("base_url", "")).rstrip("/"),
            login_id=str(zac.get("login_id", "")),
            keychain_service=str(zac.get("keychain_service", DEFAULT_KEYCHAIN_SERVICE)),
            reachability_url=str(zac.get("reachability_url", "")),
            report_url_template=str(zac.get("report_url_template", DEFAULT_ZAC_REPORT_URL_TEMPLATE)),
            selectors=_string_map(zac, "selectors", DEFAULT_ZAC_SELECTORS, parent="zac"),
            sync_work_kind=str(zac.get("sync_work_kind", DEFAULT_SYNC_WORK_KIND)),
            save_response_pattern=str(zac.get("save_response_pattern", DEFAULT_ZAC_SAVE_RESPONSE_PATTERN)),
            sales_response_pattern=str(zac.get("sales_response_pattern", DEFAULT_ZAC_SALES_RESPONSE_PATTERN)),
        ),
        schedule=ScheduleConfig(
            notify_retry_after=str(schedule.get("notify_retry_after", DEFAULT_NOTIFY_RETRY_AFTER)),
        ),
        notify=NotifyConfig(macos=bool(notify.get("macos", True))),
        logs=LogsConfig(
            dir=_path(logs.get("dir"), defaults_logs.dir),
            retention_days=int(logs.get("retention_days", defaults_logs.retention_days)),
        ),
        warnings=tuple(warnings),
    )

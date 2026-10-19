from __future__ import annotations

import io
import json
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from laborman_agent.api_client import LabormanClient
from laborman_agent.config import AgentConfig, BrowserConfig, LogsConfig, ZacConfig
from laborman_agent.context import Context
from laborman_agent.exit_codes import ExitCode
from laborman_agent.owa.fetch import HrMail, MailNotFoundError, NeedsLoginError
from laborman_agent.runner import Runner, RunOptions
from laborman_agent.zac import ZacNotImplementedError

TARGET = date(2026, 10, 9)
ENTRIES = [{"job_code": "JOB-A", "minutes": 300}, {"job_code": "JOB-B", "minutes": 210}]


def draft(**overrides: Any) -> dict[str, Any]:
    return {
        "work_date": "2026-10-09",
        "attendance": {"start": "09:02", "end": "18:41", "source": "hr_mail"},
        "breaks": [{"start": "12:00", "end": "13:00"}],
        "entries": ENTRIES,
        "issues": [],
        "registrable": True,
        "auto_allowed": True,
        "zac_registered_at": None,
        **overrides,
    }


MISSING_ATTENDANCE = draft(
    attendance=None,
    entries=[],
    issues=[{"code": "ATTENDANCE_MISSING", "severity": "error", "message": "出退勤（人事メール）が未取込です"}],
    registrable=False,
    auto_allowed=False,
)


@dataclass
class FakeApi:
    drafts: list[dict[str, Any]] = field(default_factory=lambda: [draft()])
    mode: str = "dry_run"
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    puts: list[dict[str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path.endswith("/zac-draft"):
            # 取込後は次のドラフトを返す
            current = self.drafts[0] if len(self.drafts) == 1 or not self.puts else self.drafts[1]
            return httpx.Response(200, json=current)
        if path == "/api/automation-settings":
            return httpx.Response(
                200, json={"zac_submit_mode": self.mode, "hr_mail_subject_keyword": "[勤怠情報]", "hr_mail_from": ""}
            )
        if path == "/api/zac-sync-runs" and request.method == "POST":
            run = {"id": f"run-{len(self.runs) + 1}", "status": "running", **body}
            self.runs[run["id"]] = run
            return httpx.Response(201, json=run)
        if path.startswith("/api/zac-sync-runs/") and request.method == "PATCH":
            run_id = path.rsplit("/", 1)[1]
            self.runs.setdefault(run_id, {"id": run_id}).update(body)
            return httpx.Response(200, json=self.runs[run_id])
        if path.endswith("/attendance"):
            self.puts.append(body)
            return httpx.Response(200, json={})
        if path.startswith("/api/work-reports/"):
            return httpx.Response(200, json={"attendance_source": None, "attendance_kind": "work"})
        return httpx.Response(404, json={"detail": "Not Found"})

    @property
    def last_run(self) -> dict[str, Any]:
        return list(self.runs.values())[-1]


@dataclass
class FakePage:
    login_page: bool = False
    # サインインでセッションが戻るか
    login_works: bool = True
    logins: list[tuple[str, str]] = field(default_factory=list)
    existing: bool = False
    saved: bool = True
    error: bool = False
    calls: list[str] = field(default_factory=list)

    def open(self, work_date: date) -> None:
        self.calls.append(f"open {work_date.isoformat()}")

    def is_login_page(self) -> bool:
        return self.login_page

    def login(self, login_id: str, password: str) -> None:
        self.logins.append((login_id, password))
        self.calls.append("login")
        if self.login_works:
            self.login_page = False

    def has_existing_entries(self) -> bool:
        return self.existing

    def fill(self, draft: dict[str, Any]) -> None:
        self.calls.append(f"fill {len(draft['entries'])}")

    def fill_breaks(self, breaks: list[dict[str, str]]) -> None:
        self.calls.append(f"fill_breaks {breaks}")

    def screenshot(self, path: Path) -> None:
        path.write_bytes(b"png")
        self.calls.append("screenshot")

    def click_save(self) -> None:
        self.calls.append("click_save")

    def wait_saved(self, timeout_seconds: float) -> bool:
        self.calls.append(f"wait_saved {int(timeout_seconds)}")
        return self.saved

    def has_error(self) -> bool:
        return self.error


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class Harness:
    api: FakeApi
    page: FakePage
    notifier: FakeNotifier
    ctx: Context
    sessions: list[bool]
    out: io.StringIO
    err: io.StringIO
    reachable: bool = True
    clock: datetime = datetime(2026, 10, 13, 9, 20)
    mail: HrMail | Exception = field(default_factory=lambda: HrMail("[勤怠情報]2026/10/09:開始09:02/終了18:41", None))
    session_error: Exception | None = None
    password: str | None = "s3cr3t-pw"

    def runner(self) -> Runner:
        @contextmanager
        def session(config: AgentConfig, headed: bool) -> Iterator[FakePage]:
            if self.session_error:
                raise self.session_error
            self.sessions.append(headed)
            yield self.page

        def fetcher(config: AgentConfig, target: date, keyword: str, sender: str) -> HrMail:
            if isinstance(self.mail, Exception):
                raise self.mail
            return self.mail

        return Runner(
            self.ctx,
            fetcher=fetcher,
            zac_session=session,
            reachable=lambda url: self.reachable,
            now=lambda: self.clock,
            password_reader=lambda service, login_id: self.password,
        )

    def run(self, **options: Any) -> ExitCode:
        return self.runner().run(TARGET, RunOptions(**options))


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    api = FakeApi()
    notifier = FakeNotifier()
    out, err = io.StringIO(), io.StringIO()
    config = AgentConfig(
        path=tmp_path / "config.toml",
        exists=False,
        state_dir=tmp_path / "state",
        browser=BrowserConfig(profile_dir=tmp_path / "profiles"),
        logs=LogsConfig(dir=tmp_path / "logs"),
        zac=ZacConfig(base_url="https://zac.example.test", login_id="yu-suda"),
    )
    client = LabormanClient("http://laborman.test", transport=httpx.MockTransport(api.handler))
    ctx = Context(config=config, client=client, notifier=notifier, out=out, err=err)
    return Harness(api, FakePage(), notifier, ctx, [], out, err)


# ---- design D5 の表 ----


def test_registered_day_is_skipped_without_record(harness: Harness) -> None:
    harness.api.drafts = [draft(zac_registered_at="2026-10-12T00:20:00Z")]
    assert harness.run() == ExitCode.OK
    assert harness.api.runs == {}
    assert harness.sessions == []


def test_force_runs_registered_day(harness: Harness) -> None:
    harness.api.drafts = [draft(zac_registered_at="2026-10-12T00:20:00Z")]
    assert harness.run(force=True) == ExitCode.OK
    assert harness.api.last_run["status"] == "dry_run_done"


def test_vpn_unreachable_notifies_only_on_last_attempt(harness: Harness) -> None:
    harness.reachable = False
    assert harness.run() == ExitCode.RETRY_LATER
    assert harness.api.last_run["status"] == "vpn_unreachable"
    assert harness.notifier.messages == []

    harness.clock = datetime(2026, 10, 13, 13, 20)
    assert harness.run() == ExitCode.RETRY_LATER
    assert len(harness.notifier.messages) == 1
    assert "VPN" in harness.notifier.messages[0]


def test_imports_attendance_when_missing_then_registers(harness: Harness) -> None:
    harness.api.drafts = [MISSING_ATTENDANCE, draft()]
    assert harness.run() == ExitCode.OK
    assert len(harness.api.puts) == 1
    assert harness.api.puts[0]["source"] == "hr_mail"
    assert harness.api.last_run["status"] == "dry_run_done"


def test_register_does_not_import_attendance(harness: Harness) -> None:
    harness.api.drafts = [MISSING_ATTENDANCE]
    assert harness.run(import_attendance=False) == ExitCode.NEEDS_ATTENTION
    assert harness.api.puts == []
    assert harness.api.last_run["status"] == "validation_failed"


def test_hr_mail_not_found(harness: Harness) -> None:
    harness.api.drafts = [MISSING_ATTENDANCE]
    harness.mail = MailNotFoundError("none")
    assert harness.run() == ExitCode.RETRY_LATER
    assert harness.api.last_run["status"] == "hr_mail_not_found"
    assert harness.sessions == []


def test_owa_needs_login(harness: Harness) -> None:
    harness.api.drafts = [MISSING_ATTENDANCE]
    harness.mail = NeedsLoginError("login")
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "needs_login"


def test_validation_error_stops_before_zac(harness: Harness) -> None:
    harness.api.drafts = [
        draft(
            issues=[{"code": "BREAK_MISSING", "severity": "error", "message": "休憩が記録されていません"}],
            registrable=False,
            auto_allowed=False,
        )
    ]
    assert harness.run(mode="auto") == ExitCode.NEEDS_ATTENTION
    run = harness.api.last_run
    assert run["status"] == "validation_failed"
    assert run["entries"] == ENTRIES
    assert harness.sessions == []
    assert harness.notifier.messages == ["2026-10-09: zac 登録を中止しました（休憩が記録されていません）"]


def test_signs_in_with_keychain_password_and_continues(harness: Harness) -> None:
    harness.page.login_page = True
    assert harness.run() == ExitCode.OK
    assert harness.page.logins == [("yu-suda", "s3cr3t-pw")]
    assert harness.page.calls[:3] == ["open 2026-10-09", "login", "open 2026-10-09"]
    assert harness.api.last_run["status"] == "dry_run_done"
    assert_password_not_leaked(harness)


def test_needs_login_when_password_is_not_registered(harness: Harness) -> None:
    harness.page.login_page = True
    harness.password = None
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "needs_login"
    assert "security add-generic-password -s laborman-agent.zac -a yu-suda -w" in harness.notifier.messages[0]
    assert harness.page.calls == ["open 2026-10-09"]


def test_needs_login_when_sign_in_does_not_work(harness: Harness) -> None:
    harness.page.login_page = True
    harness.page.login_works = False
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "needs_login"
    # パスワードは読めたので「未登録」ではなく、サインインの失敗として知らせる
    assert "パスワードは読めましたが、サインインに失敗しました" in harness.api.last_run["message"]
    assert_password_not_leaked(harness)


def test_password_is_not_leaked_when_login_raises(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    class BrokenLoginPage(FakePage):
        def login(self, login_id: str, password: str) -> None:
            raise RuntimeError(f"fill failed with {password}")

    harness.page = BrokenLoginPage(login_page=True)
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "needs_login"
    assert "s3cr3t-pw" not in caplog.text
    assert_password_not_leaked(harness)


def assert_password_not_leaked(harness: Harness) -> None:
    recorded = json.dumps(harness.api.runs, ensure_ascii=False)
    outputs = harness.out.getvalue() + harness.err.getvalue() + "".join(harness.notifier.messages)
    assert "s3cr3t-pw" not in recorded
    assert "s3cr3t-pw" not in outputs


def test_existing_entries_in_zac_are_not_overwritten(harness: Harness) -> None:
    harness.page.existing = True
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "already_registered_in_zac"
    assert harness.page.calls == ["open 2026-10-09"]


def test_dry_run_fills_and_screenshots_without_saving(harness: Harness, tmp_path: Path) -> None:
    assert harness.run() == ExitCode.OK
    run = harness.api.last_run
    assert run["status"] == "dry_run_done"
    assert run["entries"] == ENTRIES
    assert run["mode"] == "dry_run"
    assert harness.page.calls == [
        "open 2026-10-09",
        "fill 2",
        "fill_breaks [{'start': '12:00', 'end': '13:00'}]",
        "screenshot",
    ]
    shot = Path(run["screenshot_path"])
    assert shot.parent == tmp_path / "logs" / "screenshots"
    assert stat.S_IMODE(shot.stat().st_mode) == 0o600
    assert stat.S_IMODE(shot.parent.stat().st_mode) == 0o700
    # 定時実行の dry_run は通知しない
    assert harness.notifier.messages == []
    assert harness.sessions == [False]


def test_auto_with_warning_is_downgraded_to_dry_run(harness: Harness) -> None:
    harness.api.drafts = [draft(auto_allowed=False)]
    assert harness.run(mode="auto") == ExitCode.OK
    assert harness.api.last_run["status"] == "dry_run_done"
    assert "click_save" not in harness.page.calls
    assert any("降格" in message for message in harness.notifier.messages)


def test_assist_waits_for_user_save(harness: Harness) -> None:
    assert harness.run(mode="assist") == ExitCode.OK
    assert harness.api.last_run["status"] == "succeeded"
    assert "click_save" not in harness.page.calls
    assert "wait_saved 900" in harness.page.calls
    # assist は画面付きブラウザで開く
    assert harness.sessions == [True]


def test_assist_timeout(harness: Harness) -> None:
    harness.page.saved = False
    assert harness.run(mode="assist") == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "awaiting_user"


def test_auto_saves_and_confirms(harness: Harness) -> None:
    assert harness.run(mode="auto") == ExitCode.OK
    assert harness.api.last_run["status"] == "succeeded"
    assert harness.page.calls[-2:] == ["click_save", "wait_saved 60"]


def test_auto_save_not_confirmed(harness: Harness) -> None:
    harness.page.saved = False
    assert harness.run(mode="auto") == ExitCode.NEEDS_ATTENTION
    run = harness.api.last_run
    assert run["status"] == "failed"
    assert run["screenshot_path"]


def test_auto_save_with_error_message(harness: Harness) -> None:
    harness.page.error = True
    assert harness.run(mode="auto") == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "failed"


def test_mode_defaults_to_settings(harness: Harness) -> None:
    harness.api.mode = "assist"
    assert harness.run() == ExitCode.OK
    assert harness.api.last_run["mode"] == "assist"
    assert harness.api.last_run["status"] == "succeeded"


def test_zac_not_configured(harness: Harness) -> None:
    harness.ctx.config = AgentConfig(**{**harness.ctx.config.__dict__, "zac": ZacConfig()})
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "failed"
    assert "[zac]" in harness.api.last_run["message"]


def test_zac_page_not_implemented_yet(harness: Harness) -> None:
    harness.session_error = ZacNotImplementedError("zac の画面操作はまだ実装されていません")
    assert harness.run() == ExitCode.NEEDS_ATTENTION
    assert harness.api.last_run["status"] == "failed"
    assert "まだ実装されていません" in harness.api.last_run["message"]


def test_unexpected_error_is_recorded_as_failed(harness: Harness) -> None:
    class BrokenPage(FakePage):
        def fill(self, draft: dict[str, Any]) -> None:
            raise RuntimeError("unexpected")

    harness.page = BrokenPage()
    assert harness.run() == ExitCode.ERROR
    assert harness.api.last_run["status"] == "failed"
    assert "ログを確認" in harness.api.last_run["message"]


def test_request_updates_given_run_and_always_notifies(harness: Harness) -> None:
    harness.api.runs["req-1"] = {"id": "req-1", "status": "running", "mode": "dry_run"}
    assert harness.run(run_id="req-1", mode="dry_run", interactive=True) == ExitCode.OK
    assert list(harness.api.runs) == ["req-1"]
    assert harness.api.runs["req-1"]["status"] == "dry_run_done"
    assert harness.notifier.messages == ["2026-10-09: zac に入力しました（保存していません）"]


def test_request_for_registered_day_is_closed(harness: Harness) -> None:
    harness.api.drafts = [draft(zac_registered_at="2026-10-12T00:20:00Z")]
    harness.api.runs["req-1"] = {"id": "req-1", "status": "running"}
    assert harness.run(run_id="req-1", interactive=True) == ExitCode.OK
    assert harness.api.runs["req-1"]["status"] == "already_registered_in_zac"
    assert harness.sessions == []

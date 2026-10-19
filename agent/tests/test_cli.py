from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
import json
import stat
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from laborman_agent.api_client import LabormanClient
from laborman_agent.cli import doctor, main, process_requests, run_fetch_attendance, run_zac, sync_zac
from laborman_agent.context import Context
from laborman_agent.config import AgentConfig, BrowserConfig, LogsConfig, ZacConfig
from laborman_agent.exit_codes import ExitCode
from laborman_agent.lock import acquire_lock
from laborman_agent.owa.fetch import HrMail, MailNotFoundError, NeedsLoginError
from laborman_agent.runner import RunOptions

TARGET = date(2026, 10, 9)
SUBJECT = "[勤怠情報]2026/10/09:開始08:29/終了18:38"


@dataclass
class FakeApi:
    report: dict[str, Any] = field(
        default_factory=lambda: {"work_date": "2026-10-09", "attendance_source": None, "attendance_kind": "work"}
    )
    settings: dict[str, Any] = field(default_factory=lambda: {"hr_mail_subject_keyword": "[勤怠情報]", "hr_mail_from": ""})
    puts: list[dict[str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/automation-settings":
            return httpx.Response(200, json=self.settings)
        if request.method == "PUT" and path.endswith("/attendance"):
            if self.report["attendance_source"] == "manual":
                return httpx.Response(409, json={"detail": {"message": "手入力済み", "conflicts": []}})
            body = json.loads(request.content)
            self.puts.append(body)
            self.report.update(attendance_source=body["source"], attendance_kind=body["kind"])
            return httpx.Response(200, json=self.report)
        if path.startswith("/api/work-reports/"):
            return httpx.Response(200, json=self.report)
        return httpx.Response(404, json={"detail": "Not Found"})


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)


class FakeFetcher:
    def __init__(self, result: HrMail | Exception) -> None:
        self.result = result
        self.calls: list[tuple[date, str, str]] = []

    def __call__(self, config: AgentConfig, target: date, keyword: str, sender: str) -> HrMail:
        self.calls.append((target, keyword, sender))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture()
def config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        path=tmp_path / "config.toml",
        exists=False,
        state_dir=tmp_path / "state",
        browser=BrowserConfig(profile_dir=tmp_path / "profiles"),
        logs=LogsConfig(dir=tmp_path / "logs"),
    )


@dataclass
class Harness:
    ctx: Context
    api: FakeApi
    notifier: FakeNotifier
    out: io.StringIO
    err: io.StringIO

    def run(self, fetcher: FakeFetcher, date_arg: str | None = "2026-10-09") -> ExitCode:
        return run_fetch_attendance(self.ctx, date_arg, fetcher, today=date(2026, 10, 13))


@pytest.fixture()
def harness(config: AgentConfig) -> Harness:
    api = FakeApi()
    notifier = FakeNotifier()
    out, err = io.StringIO(), io.StringIO()
    client = LabormanClient("http://laborman.test", transport=httpx.MockTransport(api.handler))
    ctx = Context(config=config, client=client, notifier=notifier, out=out, err=err)
    return Harness(ctx, api, notifier, out, err)


def test_imports_attendance_from_subject(harness: Harness) -> None:
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))

    assert harness.run(fetcher) == ExitCode.OK

    assert fetcher.calls == [(TARGET, "[勤怠情報]", "")]
    assert harness.api.puts == [
        {
            "start_at": "2026-10-09T08:29:00+09:00",
            "end_at": "2026-10-09T18:38:00+09:00",
            "source": "hr_mail",
            "kind": "work",
        }
    ]
    assert "08:29–18:38 を登録しました" in harness.out.getvalue()
    assert harness.notifier.messages == []


def test_defaults_to_previous_business_day(harness: Harness) -> None:
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))
    # 10/13（火）の前営業日は 10/12（祝日）を飛ばして 10/9（金）
    assert harness.run(fetcher, date_arg=None) == ExitCode.OK
    assert fetcher.calls[0][0] == TARGET


def test_passes_sender_when_configured(harness: Harness) -> None:
    harness.api.settings["hr_mail_from"] = "hr@example.com"
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))
    harness.run(fetcher)
    assert fetcher.calls == [(TARGET, "[勤怠情報]", "hr@example.com")]


def test_mail_not_found_exits_2_with_leave_hint(harness: Harness) -> None:
    assert harness.run(FakeFetcher(MailNotFoundError("none"))) == ExitCode.RETRY_LATER

    assert harness.api.puts == []
    assert "休暇" in harness.err.getvalue()
    assert any("休暇" in message for message in harness.notifier.messages)


def test_parse_failure_exits_3_and_saves_mail(harness: Harness, config: AgentConfig) -> None:
    fetcher = FakeFetcher(HrMail(subject="[勤怠情報]2026/10/09 のお知らせ", body="書式が変わった本文"))

    assert harness.run(fetcher) == ExitCode.NEEDS_ATTENTION

    assert harness.api.puts == []
    saved = list((config.logs.dir / "hr_mail").glob("*.txt"))
    assert len(saved) == 1
    assert stat.S_IMODE(saved[0].stat().st_mode) == 0o600
    assert "書式が変わった本文" in saved[0].read_text(encoding="utf-8")
    assert harness.notifier.messages == ["2026-10-09: 人事メールを解析できませんでした"]
    # 本文は通知・出力に含めない
    assert "書式が変わった本文" not in harness.err.getvalue() + harness.out.getvalue()


def test_parse_failure_for_other_day(harness: Harness) -> None:
    fetcher = FakeFetcher(HrMail(subject="[勤怠情報]2026/10/08:開始09:01/終了18:12", body=None))
    assert harness.run(fetcher) == ExitCode.NEEDS_ATTENTION
    assert harness.api.puts == []


@pytest.mark.parametrize("kind", ["work", "leave"])
def test_manual_day_is_skipped_without_opening_owa(harness: Harness, kind: str) -> None:
    harness.api.report.update(attendance_source="manual", attendance_kind=kind)
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))

    assert harness.run(fetcher) == ExitCode.OK

    assert fetcher.calls == []
    assert harness.api.puts == []
    assert "スキップ" in harness.out.getvalue()


def test_conflict_on_put_is_treated_as_skip(harness: Harness) -> None:
    class ManualAfterFetch(FakeFetcher):
        def __call__(self, config: AgentConfig, target: date, keyword: str, sender: str) -> HrMail:
            # 取得中に利用者が手入力した場合
            harness.api.report["attendance_source"] = "manual"
            return super().__call__(config, target, keyword, sender)

    assert harness.run(ManualAfterFetch(HrMail(subject=SUBJECT, body=None))) == ExitCode.OK
    assert harness.api.puts == []
    assert "上書きしませんでした" in harness.out.getvalue()


def test_needs_login_exits_3_and_notifies(harness: Harness) -> None:
    assert harness.run(FakeFetcher(NeedsLoginError("login"))) == ExitCode.NEEDS_ATTENTION
    assert any("サインイン" in message for message in harness.notifier.messages)


def test_missing_keyword_exits_3_without_opening_owa(harness: Harness) -> None:
    harness.api.settings["hr_mail_subject_keyword"] = ""
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))
    assert harness.run(fetcher) == ExitCode.NEEDS_ATTENTION
    assert fetcher.calls == []


def test_lock_held_exits_0_without_work(harness: Harness, config: AgentConfig) -> None:
    fetcher = FakeFetcher(HrMail(subject=SUBJECT, body=None))
    with acquire_lock(config.lock_path):
        assert harness.run(fetcher) == ExitCode.OK
    assert fetcher.calls == []
    assert "実行中" in harness.out.getvalue()


# ---- doctor ----


def test_doctor_all_ok(harness: Harness, config: AgentConfig) -> None:
    config.path.write_text("", encoding="utf-8")
    config.path.chmod(0o600)
    for name in ("owa", "zac"):
        (config.browser.profile_dir / name).mkdir(parents=True, mode=0o700)
    ctx = Context(
        config=AgentConfig(
            **{
                **config.__dict__,
                "exists": True,
                "zac": ZacConfig(base_url="https://zac.example.test", login_id="yu-suda"),
            }
        ),
        client=harness.ctx.client,
        notifier=harness.ctx.notifier,
        out=harness.out,
        err=harness.err,
    )

    assert (
        doctor(
            ctx,
            browser_check=lambda _: (True, "chrome を起動できます"),
            reachable=lambda _: True,
            password_check=lambda service, login_id: True,
        )
        == ExitCode.OK
    )
    assert "[OK] zac のパスワード: キーチェーンに登録済み（laborman-agent.zac / yu-suda）" in harness.out.getvalue()
    assert "[NG]" not in harness.out.getvalue()


def test_doctor_reports_failures(harness: Harness) -> None:
    assert (
        doctor(harness.ctx, browser_check=lambda _: (False, "chrome を起動できません"), reachable=lambda _: True)
        == ExitCode.NEEDS_ATTENTION
    )
    output = harness.out.getvalue()
    assert "[NG] 設定ファイル" in output
    assert "[NG] OWA プロファイル" in output
    assert "laborman-agent login owa" in output
    assert "[NG] ブラウザ" in output
    assert "[OK] laborman API" in output
    assert "[NG] zac: URL が未設定です" in output


def test_doctor_reports_unreachable_zac(harness: Harness) -> None:
    ctx = Context(
        config=AgentConfig(**{**harness.ctx.config.__dict__, "zac": ZacConfig(base_url="https://zac.example.test")}),
        client=harness.ctx.client,
        notifier=harness.ctx.notifier,
        out=harness.out,
        err=harness.err,
    )
    assert (
        doctor(ctx, browser_check=lambda _: (True, "ok"), reachable=lambda _: False) == ExitCode.NEEDS_ATTENTION
    )
    output = harness.out.getvalue()
    assert "[NG] zac への到達性: https://zac.example.test に接続できません（VPN を確認してください）" in output
    assert "[NG] zac プロファイル" in output
    assert "login zac" in output
    assert "[NG] zac のパスワード: config.toml の [zac] login_id が未設定です" in output


def test_doctor_reports_missing_keychain_password(harness: Harness) -> None:
    ctx = Context(
        config=AgentConfig(
            **{**harness.ctx.config.__dict__, "zac": ZacConfig(base_url="https://zac.example.test", login_id="yu-suda")}
        ),
        client=harness.ctx.client,
        notifier=harness.ctx.notifier,
        out=harness.out,
        err=harness.err,
    )
    doctor(ctx, browser_check=lambda _: (True, "ok"), reachable=lambda _: True, password_check=lambda s, a: False)
    assert "security add-generic-password -s laborman-agent.zac -a yu-suda -w" in harness.out.getvalue()


# ---- main ----


def write_config(tmp_path: Path, api_base_url: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"""
[laborman]
api_base_url = "{api_base_url}"
state_dir = "{tmp_path / 'state'}"

[notify]
macos = false

[logs]
dir = "{tmp_path / 'logs'}"
""",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_main_exits_1_when_api_is_unreachable(tmp_path: Path) -> None:
    err = io.StringIO()
    # 使われていないポートに接続させる
    code = main(
        ["--config", str(write_config(tmp_path, "http://127.0.0.1:9")), "fetch-attendance", "--date", "2026-10-09"],
        out=io.StringIO(),
        err=err,
    )
    assert code == ExitCode.ERROR
    assert "接続できません" in err.getvalue()


def test_main_rejects_invalid_date(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--config", str(write_config(tmp_path, "http://127.0.0.1:9")), "fetch-attendance", "--date", "2026/10/09"])
    assert info.value.code == 2


def test_main_warns_about_loose_config_permission(tmp_path: Path) -> None:
    path = write_config(tmp_path, "http://127.0.0.1:9")
    path.chmod(0o644)
    err = io.StringIO()
    main(["--config", str(path), "fetch-attendance", "--date", "2026-10-09"], out=io.StringIO(), err=err)
    assert "chmod 600" in err.getvalue()


def test_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    output = capsys.readouterr().out
    for command in ["login", "fetch-attendance", "doctor"]:
        assert command in output


# ---- run / register / process-requests ----


class RecordingRunner:
    def __init__(self, code: ExitCode = ExitCode.OK) -> None:
        self.code = code
        self.calls: list[tuple[date, RunOptions]] = []

    def __call__(self, ctx: Context) -> RecordingRunner:
        return self

    def run(self, target: date, options: RunOptions = RunOptions()) -> ExitCode:
        self.calls.append((target, options))
        return self.code


def requests_api(
    requests: list[dict[str, object]], conflicts: frozenset[str] = frozenset()
) -> tuple[LabormanClient, list[str]]:
    claimed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/zac-sync-runs" and request.method == "GET":
            assert request.url.params["status"] == "requested"
            assert request.url.params["order"] == "asc"
            return httpx.Response(200, json=requests)
        if request.url.path.endswith("/claim"):
            run_id = request.url.path.split("/")[-2]
            if run_id in conflicts:
                return httpx.Response(409, json={"detail": {"message": "取り消されています", "conflicts": []}})
            claimed.append(run_id)
            found = next(item for item in requests if item["id"] == run_id)
            return httpx.Response(200, json={**found, "status": "running"})
        return httpx.Response(404, json={"detail": "Not Found"})

    return LabormanClient("http://laborman.test", transport=httpx.MockTransport(handler)), claimed


def make_ctx(harness: Harness, client: LabormanClient) -> Context:
    return Context(config=harness.ctx.config, client=client, notifier=harness.ctx.notifier, out=harness.out, err=harness.err)


def test_process_requests_without_requests_does_nothing(harness: Harness) -> None:
    client, claimed = requests_api([])
    runner = RecordingRunner()
    assert process_requests(make_ctx(harness, client), runner_factory=runner) == ExitCode.OK
    assert runner.calls == []
    assert claimed == []


def test_process_requests_runs_claimed_requests_in_order(harness: Harness) -> None:
    client, claimed = requests_api(
        [
            {"id": "req-1", "work_date": "2026-10-08", "mode": "dry_run", "status": "requested"},
            {"id": "req-2", "work_date": "2026-10-09", "mode": "assist", "status": "requested"},
        ],
        conflicts=frozenset({"req-1"}),
    )
    runner = RecordingRunner(ExitCode.NEEDS_ATTENTION)

    assert process_requests(make_ctx(harness, client), runner_factory=runner) == ExitCode.NEEDS_ATTENTION

    # 取り消された（claim が 409 の）依頼は実行しない
    assert claimed == ["req-2"]
    assert len(runner.calls) == 1
    target, options = runner.calls[0]
    assert target == date(2026, 10, 9)
    assert options == RunOptions(mode="assist", run_id="req-2", interactive=True)


def test_process_requests_while_locked(harness: Harness, config: AgentConfig) -> None:
    client, claimed = requests_api([{"id": "req-1", "work_date": "2026-10-09", "mode": "dry_run", "status": "requested"}])
    runner = RecordingRunner()
    with acquire_lock(config.lock_path):
        assert process_requests(make_ctx(harness, client), runner_factory=runner) == ExitCode.OK
    assert claimed == []
    assert runner.calls == []


def test_run_resolves_target_and_options(harness: Harness) -> None:
    runner = RecordingRunner()
    options = RunOptions(mode="dry_run", headed=True)
    assert run_zac(harness.ctx, None, options, runner_factory=runner, today=date(2026, 10, 13)) == ExitCode.OK
    assert runner.calls == [(date(2026, 10, 9), options)]


def test_run_while_locked(harness: Harness, config: AgentConfig) -> None:
    runner = RecordingRunner()
    with acquire_lock(config.lock_path):
        assert run_zac(harness.ctx, "2026-10-09", RunOptions(), runner_factory=runner) == ExitCode.OK
    assert runner.calls == []
    assert "実行中" in harness.out.getvalue()


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["run"], RunOptions(import_attendance=True)),
        (["run", "--date", "2026-10-09", "--mode", "auto", "--headed", "--force"], RunOptions(mode="auto", headed=True, force=True)),
        (["register", "--mode", "assist"], RunOptions(mode="assist", import_attendance=False)),
    ],
)
def test_run_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: RunOptions
) -> None:
    seen: list[tuple[str | None, RunOptions]] = []

    def fake_run_zac(ctx: Context, date_arg: str | None, options: RunOptions, *args: object, **kwargs: object) -> ExitCode:
        seen.append((date_arg, options))
        return ExitCode.OK

    monkeypatch.setattr("laborman_agent.cli.run_zac", fake_run_zac)
    assert main(["--config", str(write_config(tmp_path, "http://127.0.0.1:9")), *argv], out=io.StringIO(), err=io.StringIO()) == 0
    assert seen[0][1] == expected


def test_run_rejects_invalid_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--config", str(write_config(tmp_path, "http://127.0.0.1:9")), "run", "--mode", "submit"])
    assert info.value.code == 2


# ---- sync-zac ----


class FakeReader:
    def __init__(self, login_page: bool = False, error: Exception | None = None) -> None:
        self.login_page = login_page
        self.error = error
        self.calls: list[str] = []

    def open(self, work_date: date) -> None:
        self.calls.append(f"open {work_date.isoformat()}")

    def is_login_page(self) -> bool:
        return self.login_page

    def login(self, login_id: str, password: str) -> None:
        self.calls.append(f"login {login_id}")
        self.login_page = False

    def read_masters(self) -> Any:
        from laborman_agent.zac.report_page import ZacMasters

        if self.error:
            raise self.error
        self.calls.append("read")
        return ZacMasters(
            work_kinds=["プロジェクト作業"],
            projects=[{"code": "2602063", "name": "bizoceanAPPs開発(26/11)", "sales_items": [{"name": "bizoceanAPPs開発(26/11)", "is_closed": False}]}],
        )


def sync_api() -> tuple[LabormanClient, list[dict[str, Any]]]:
    imported: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/zac-masters/import"
        imported.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "created": {"work_kinds": 0, "jobs": 1, "sales_items": 1},
                "updated": {"work_kinds": 0, "jobs": 0, "sales_items": 0},
                "missing_jobs": ["2602061"],
            },
        )

    return LabormanClient("http://laborman.test", transport=httpx.MockTransport(handler)), imported


def zac_ctx(harness: Harness, client: LabormanClient) -> Context:
    config = AgentConfig(
        **{**harness.ctx.config.__dict__, "zac": ZacConfig(base_url="https://zac.example.test", login_id="yu-suda")}
    )
    return Context(config=config, client=client, notifier=harness.ctx.notifier, out=harness.out, err=harness.err)


def reader_factory(reader: FakeReader) -> Any:
    @contextmanager
    def factory(config: AgentConfig) -> Iterator[FakeReader]:
        yield reader

    return factory


def test_sync_zac_imports_masters(harness: Harness) -> None:
    client, imported = sync_api()
    reader = FakeReader()

    code = sync_zac(zac_ctx(harness, client), None, reader_factory(reader), reachable=lambda _: True, today=date(2026, 10, 14))

    assert code == ExitCode.OK
    assert reader.calls == ["open 2026-10-14", "read"]
    assert imported[0]["projects"][0]["code"] == "2602063"
    output = harness.out.getvalue()
    assert "案件 1 件" in output
    assert "2602061" in output and "無効化はしていません" in output


def test_sync_zac_signs_in_with_keychain(harness: Harness) -> None:
    client, imported = sync_api()
    reader = FakeReader(login_page=True)
    code = sync_zac(
        zac_ctx(harness, client),
        "2026-10-13",
        reader_factory(reader),
        reachable=lambda _: True,
        password_reader=lambda service, login_id: "s3cr3t-pw",
    )
    assert code == ExitCode.OK
    assert reader.calls == ["open 2026-10-13", "login yu-suda", "open 2026-10-13", "read"]
    assert "s3cr3t-pw" not in harness.out.getvalue() + harness.err.getvalue()


def test_sync_zac_without_password(harness: Harness) -> None:
    client, imported = sync_api()
    code = sync_zac(
        zac_ctx(harness, client),
        None,
        reader_factory(FakeReader(login_page=True)),
        reachable=lambda _: True,
        password_reader=lambda service, login_id: None,
    )
    assert code == ExitCode.NEEDS_ATTENTION
    assert imported == []
    assert "security add-generic-password" in harness.err.getvalue()


def test_sync_zac_vpn_unreachable(harness: Harness) -> None:
    client, imported = sync_api()
    code = sync_zac(zac_ctx(harness, client), None, reader_factory(FakeReader()), reachable=lambda _: False)
    assert code == ExitCode.RETRY_LATER
    assert imported == []


def test_sync_zac_page_error(harness: Harness) -> None:
    from laborman_agent.zac.report_page import ZacPageError

    client, imported = sync_api()
    reader = FakeReader(error=ZacPageError("作業登録を開けません（確定済みの日は登録できません）"))
    code = sync_zac(zac_ctx(harness, client), None, reader_factory(reader), reachable=lambda _: True)
    assert code == ExitCode.NEEDS_ATTENTION
    assert imported == []
    assert "確定済み" in harness.err.getvalue()

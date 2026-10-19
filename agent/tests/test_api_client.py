from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from laborman_agent.api_client import (
    ApiError,
    ApiUnavailableError,
    AttendanceConflictError,
    ConflictError,
    LabormanClient,
)

JST = ZoneInfo("Asia/Tokyo")


def client_for(handler: httpx.MockTransport) -> LabormanClient:
    return LabormanClient("http://laborman.test", transport=handler)


def test_health_report_and_settings() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/work-reports/2026-10-09":
            return httpx.Response(200, json={"work_date": "2026-10-09", "attendance_source": None})
        return httpx.Response(200, json={"hr_mail_subject_keyword": "[勤怠情報]", "hr_mail_from": ""})

    with client_for(httpx.MockTransport(handler)) as client:
        assert client.health() == {"status": "ok"}
        assert client.get_report(date(2026, 10, 9))["attendance_source"] is None
        assert client.get_automation_settings()["hr_mail_subject_keyword"] == "[勤怠情報]"
    assert seen == [
        "GET /api/health",
        "GET /api/work-reports/2026-10-09",
        "GET /api/automation-settings",
    ]


def test_put_attendance_sends_hr_mail_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"attendance_source": "hr_mail"})

    with client_for(httpx.MockTransport(handler)) as client:
        client.put_attendance(
            date(2026, 10, 9),
            datetime(2026, 10, 9, 8, 29, tzinfo=JST),
            datetime(2026, 10, 9, 18, 38, tzinfo=JST),
        )
    assert captured == {
        "method": "PUT",
        "path": "/api/work-reports/2026-10-09/attendance",
        "body": {
            "start_at": "2026-10-09T08:29:00+09:00",
            "end_at": "2026-10-09T18:38:00+09:00",
            "source": "hr_mail",
            "kind": "work",
        },
    }


def test_conflict_is_reported_separately() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"message": "手入力済み", "conflicts": []}})

    with client_for(httpx.MockTransport(handler)) as client, pytest.raises(AttendanceConflictError) as info:
        client.put_attendance(date(2026, 10, 9), None, None)
    assert info.value.message == "手入力済み"


def test_validation_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "終了時刻は開始時刻より後にしてください"})

    with client_for(httpx.MockTransport(handler)) as client, pytest.raises(ApiError) as info:
        client.put_attendance(date(2026, 10, 9), None, None)
    assert info.value.status_code == 422
    assert "終了時刻" in info.value.message


def test_connection_failure_is_api_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with client_for(httpx.MockTransport(handler)) as client, pytest.raises(ApiUnavailableError) as info:
        client.health()
    assert "接続できません" in str(info.value)


# ---- zac 連携 ----


def test_zac_endpoints() -> None:
    seen: list[tuple[str, str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, str(request.url.params), body))
        if request.url.path == "/api/zac-sync-runs" and request.method == "GET":
            return httpx.Response(200, json=[{"id": "r1", "status": "requested"}])
        if request.method == "POST" and request.url.path == "/api/zac-sync-runs":
            return httpx.Response(201, json={"id": "r2", "status": "running"})
        return httpx.Response(200, json={"id": "r1", "registrable": True})

    with client_for(httpx.MockTransport(handler)) as client:
        assert client.get_zac_draft(date(2026, 10, 9))["registrable"] is True
        assert client.create_zac_run(date(2026, 10, 9), "dry_run", "0.1.0")["id"] == "r2"
        client.update_zac_run("r2", status="dry_run_done", screenshot_path="/tmp/x.png")
        assert client.list_zac_runs(status="requested", oldest_first=True)[0]["id"] == "r1"
        client.claim_zac_run("r1")

    assert seen == [
        ("GET", "/api/work-reports/2026-10-09/zac-draft", "", None),
        ("POST", "/api/zac-sync-runs", "", {"work_date": "2026-10-09", "mode": "dry_run", "agent_version": "0.1.0"}),
        ("PATCH", "/api/zac-sync-runs/r2", "", {"status": "dry_run_done", "screenshot_path": "/tmp/x.png"}),
        ("GET", "/api/zac-sync-runs", "order=asc&status=requested", None),
        ("POST", "/api/zac-sync-runs/r1/claim", "", None),
    ]


def test_claim_conflict_is_generic_conflict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"message": "この依頼はすでに処理中か、取り消されています", "conflicts": []}})

    with client_for(httpx.MockTransport(handler)) as client, pytest.raises(ConflictError) as info:
        client.claim_zac_run("r1")
    assert not isinstance(info.value, AttendanceConflictError)
    assert "処理中" in info.value.message

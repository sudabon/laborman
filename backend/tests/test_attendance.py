from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import repositories

WORK_DATE = "2026-10-09"


def jst(hhmm: str, day: str = WORK_DATE) -> str:
    return f"{day}T{hhmm}:00+09:00"


def as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    # SQLite は打刻列のタイムゾーンを保持しないため、なしの値は UTC とみなす
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@pytest.fixture()
def set_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def apply(value: str) -> None:
        monkeypatch.setattr(repositories, "now_utc", lambda: as_utc(value))

    return apply


def put_attendance(
    client: TestClient,
    start: str | None,
    end: str | None,
    source: str = "hr_mail",
    kind: str = "work",
    day: str = WORK_DATE,
):
    return client.put(
        f"/api/work-reports/{day}/attendance",
        json={"start_at": start, "end_at": end, "source": source, "kind": kind},
    )


def same_instant(actual: str | None, expected: str) -> bool:
    return actual is not None and as_utc(actual) == as_utc(expected)


def test_report_defaults_to_no_attendance(client: TestClient) -> None:
    report = client.get(f"/api/work-reports/{WORK_DATE}").json()
    assert report["attendance_start_at"] is None
    assert report["attendance_end_at"] is None
    assert report["attendance_source"] is None
    assert report["attendance_kind"] == "work"
    assert report["attendance_imported_at"] is None


def test_hr_mail_attendance_sets_imported_at(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now("2026-10-13T09:20:00+09:00")
    response = put_attendance(client, jst("08:29"), jst("18:38"))
    assert response.status_code == 200
    body = response.json()
    assert same_instant(body["attendance_start_at"], jst("08:29"))
    assert same_instant(body["attendance_end_at"], jst("18:38"))
    assert body["attendance_source"] == "hr_mail"
    assert body["attendance_kind"] == "work"
    assert same_instant(body["attendance_imported_at"], "2026-10-13T09:20:00+09:00")


def test_attendance_is_separate_from_punch(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now(jst("09:05"))
    client.post(f"/api/work-reports/{WORK_DATE}/record-start", json={})
    set_now(jst("18:35"))
    client.post(f"/api/work-reports/{WORK_DATE}/record-end", json={})
    put_attendance(client, jst("09:02"), jst("18:41"))

    # 打刻をやり直しても出退勤実績は変わらない
    set_now(jst("18:50"))
    report = client.post(f"/api/work-reports/{WORK_DATE}/record-end", json={}).json()
    assert same_instant(report["start_time"], jst("09:05"))
    assert same_instant(report["end_time"], jst("18:50"))
    assert same_instant(report["attendance_start_at"], jst("09:02"))
    assert same_instant(report["attendance_end_at"], jst("18:41"))


def test_manual_overrides_hr_mail_and_keeps_imported_at(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now("2026-10-13T09:20:00+09:00")
    put_attendance(client, jst("09:02"), jst("18:41"))
    set_now("2026-10-13T10:00:00+09:00")
    response = put_attendance(client, jst("09:00"), jst("18:41"), source="manual")
    assert response.status_code == 200
    body = response.json()
    assert same_instant(body["attendance_start_at"], jst("09:00"))
    assert body["attendance_source"] == "manual"
    assert same_instant(body["attendance_imported_at"], "2026-10-13T09:20:00+09:00")


@pytest.mark.parametrize("kind", ["work", "leave"])
def test_hr_mail_does_not_overwrite_manual(client: TestClient, kind: str) -> None:
    if kind == "work":
        put_attendance(client, jst("09:00"), jst("18:30"), source="manual")
    else:
        put_attendance(client, None, None, source="manual", kind="leave")

    response = put_attendance(client, jst("08:29"), jst("18:38"))
    assert response.status_code == 409
    assert "message" in response.json()["detail"]

    report = client.get(f"/api/work-reports/{WORK_DATE}").json()
    assert report["attendance_source"] == "manual"
    assert report["attendance_kind"] == kind
    assert report["attendance_imported_at"] is None
    if kind == "work":
        assert same_instant(report["attendance_start_at"], jst("09:00"))
    else:
        assert report["attendance_start_at"] is None


def test_manual_leave_without_times(client: TestClient) -> None:
    response = put_attendance(client, None, None, source="manual", kind="leave")
    assert response.status_code == 200
    body = response.json()
    assert body["attendance_kind"] == "leave"
    assert body["attendance_source"] == "manual"
    assert body["attendance_start_at"] is None
    assert body["attendance_end_at"] is None


@pytest.mark.parametrize(
    "payload",
    [
        # 勤務は出勤・退勤が必須
        {"start_at": jst("09:00"), "end_at": None, "source": "manual", "kind": "work"},
        {"start_at": None, "end_at": jst("18:00"), "source": "hr_mail", "kind": "work"},
        # 退勤は出勤より後
        {"start_at": jst("18:00"), "end_at": jst("09:00"), "source": "manual", "kind": "work"},
        {"start_at": jst("09:00"), "end_at": jst("09:00"), "source": "manual", "kind": "work"},
        # 勤務日 00:00〜翌 06:00 の範囲外
        {
            "start_at": jst("23:00", "2026-10-08"),
            "end_at": jst("18:00"),
            "source": "manual",
            "kind": "work",
        },
        {
            "start_at": jst("09:00"),
            "end_at": jst("06:00", "2026-10-10"),
            "source": "manual",
            "kind": "work",
        },
        # 人事メールから休暇は来ない
        {"start_at": None, "end_at": None, "source": "hr_mail", "kind": "leave"},
        # 不正な値
        {"start_at": jst("09:00"), "end_at": jst("18:00"), "source": "zac", "kind": "work"},
        {"start_at": jst("09:00"), "end_at": jst("18:00"), "source": "manual", "kind": "half"},
        # タイムゾーンなし
        {
            "start_at": "2026-10-09T09:00:00",
            "end_at": "2026-10-09T18:00:00",
            "source": "manual",
            "kind": "work",
        },
    ],
)
def test_attendance_validation(client: TestClient, payload: dict[str, Any]) -> None:
    response = client.put(f"/api/work-reports/{WORK_DATE}/attendance", json=payload)
    assert response.status_code == 422
    report = client.get(f"/api/work-reports/{WORK_DATE}").json()
    assert report["attendance_source"] is None


def test_attendance_after_midnight_is_accepted(client: TestClient) -> None:
    # 25:30 は勤務日の翌日 01:30
    response = put_attendance(
        client, jst("09:00"), jst("01:30", "2026-10-10"), source="manual"
    )
    assert response.status_code == 200


def test_attendance_appears_in_month_list(client: TestClient) -> None:
    put_attendance(client, jst("08:29"), jst("18:38"))
    reports = client.get("/api/work-reports", params={"year": 2026, "month": 10}).json()
    assert [r["attendance_source"] for r in reports] == ["hr_mail"]


def test_automation_settings_hr_mail_conditions(client: TestClient) -> None:
    initial = client.get("/api/automation-settings").json()
    assert initial["hr_mail_from"] == ""
    assert initial["hr_mail_subject_keyword"] == ""

    saved = client.put(
        "/api/automation-settings",
        json={
            "default_break_start": "12:00",
            "default_break_end": "13:00",
            "hr_mail_from": " hr@example.com ",
            "hr_mail_subject_keyword": "[勤怠情報]",
        },
    )
    assert saved.status_code == 200
    current = client.get("/api/automation-settings").json()
    assert current["hr_mail_from"] == "hr@example.com"
    assert current["hr_mail_subject_keyword"] == "[勤怠情報]"
    assert current["default_break_start"] == "12:00"


# ---- 出退勤に合わせた最初・最後のタスクの時刻 ----


@pytest.fixture()
def job(client: TestClient) -> None:
    assert client.post("/api/jobs", json={"code": "JOB-A", "name": "A社保守"}).status_code == 201


def add_task(client: TestClient, start: str, end: str | None) -> dict[str, Any]:
    response = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks",
        json={"job_code": "JOB-A", "description": "", "start_at": start, "end_at": end},
    )
    assert response.status_code == 201
    return dict(response.json())


def task_times(client: TestClient) -> list[tuple[str | None, str | None]]:
    def hhmm(value: str | None) -> str | None:
        if value is None:
            return None
        return as_utc(value).astimezone(datetime.fromisoformat(jst("00:00")).tzinfo).strftime("%H:%M")

    tasks = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    return [(hhmm(task["start_at"]), hhmm(task["end_at"])) for task in tasks]


def test_attendance_aligns_first_start_and_last_end(client: TestClient, job: None) -> None:
    add_task(client, jst("08:15"), jst("12:00"))
    add_task(client, jst("13:00"), jst("20:20"))
    assert put_attendance(client, jst("08:14"), jst("20:23")).status_code == 200
    assert task_times(client) == [("08:14", "12:00"), ("13:00", "20:23")]


def test_attendance_shrinks_tasks_sticking_out(client: TestClient, job: None) -> None:
    add_task(client, jst("08:00"), jst("12:00"))
    add_task(client, jst("13:00"), jst("18:45"))
    assert put_attendance(client, jst("08:10"), jst("18:30"), source="manual").status_code == 200
    assert task_times(client) == [("08:10", "12:00"), ("13:00", "18:30")]


def test_attendance_leaves_large_gaps(client: TestClient, job: None) -> None:
    # 30 分を超えるずれは記録漏れの可能性があるため直さない（ドラフトの検証で知らせる）
    add_task(client, jst("09:00"), jst("17:00"))
    assert put_attendance(client, jst("08:14"), jst("17:31")).status_code == 200
    assert task_times(client) == [("09:00", "17:00")]


def test_attendance_skips_running_task_and_break_at_the_edge(client: TestClient, job: None) -> None:
    client.post(f"/api/work-reports/{WORK_DATE}/breaks", json={"start_at": jst("08:10"), "end_at": jst("08:20")})
    add_task(client, jst("08:20"), jst("12:00"))
    add_task(client, jst("13:00"), None)
    assert put_attendance(client, jst("08:05"), jst("18:00")).status_code == 200
    assert task_times(client) == [("08:20", "12:00"), ("13:00", None)]


def test_attendance_does_not_make_task_empty(client: TestClient, job: None) -> None:
    add_task(client, jst("08:00"), jst("08:10"))
    assert put_attendance(client, jst("08:20"), jst("08:30")).status_code == 200
    # 最初のタスクの開始を 08:20 にすると終了より後になるため、開始は直さない（終了は 08:30 に延ばす）
    assert task_times(client) == [("08:00", "08:30")]

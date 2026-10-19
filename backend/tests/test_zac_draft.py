from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.zac_draft import (
    AttendanceInput,
    BreakInput,
    DraftSettings,
    JobInfo,
    SalesItemInfo,
    TaskInput,
    allocate_by_largest_remainder,
    build_zac_draft,
)

TZ = ZoneInfo("Asia/Tokyo")
WORK_DATE = date(2026, 10, 9)
JOBS = {
    "JOB-A": JobInfo("JOB-A", "A社 保守", "A社保守"),
    "JOB-B": JobInfo("JOB-B", "", "社内業務"),
    "JOB-M": JobInfo("JOB-M", "", "月次案件(26/10)", valid_month="2026-10"),
}
SALES = {
    "s-a": SalesItemInfo("s-a", "JOB-A", "保守（2026／10）", "2026-10"),
    "s-a9": SalesItemInfo("s-a9", "JOB-A", "保守（2026／09）", "2026-09"),
    "s-b": SalesItemInfo("s-b", "JOB-B", "社内業務"),
    "s-m": SalesItemInfo("s-m", "JOB-M", "月次案件(26/10)", "2026-10"),
}
DEFAULT_ITEM = {"JOB-A": "s-a", "JOB-B": "s-b", "JOB-M": "s-m"}
WORK = "プロジェクト作業"


def at(hhmm: str, day: int = 9) -> datetime:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 10, day, hours, minutes, tzinfo=TZ).astimezone(UTC)


def task(
    task_id: str,
    job: str,
    description: str,
    start: str,
    end: str | None,
    end_day: int = 9,
    work_kind: str | None = WORK,
    sales_item: str | None = "default",
) -> TaskInput:
    item = DEFAULT_ITEM.get(job) if sales_item == "default" else sales_item
    return TaskInput(
        task_id, job, description, at(start), at(end, end_day) if end else None, work_kind, item
    )


def brk(break_id: str, start: str, end: str | None) -> BreakInput:
    return BreakInput(break_id, at(start), at(end) if end else None)


def attendance(start: str | None = "09:02", end: str | None = "18:41", end_day: int = 9) -> AttendanceInput:
    return AttendanceInput(
        at(start) if start else None, at(end, end_day) if end else None, "hr_mail", "work"
    )


SPEC_TASKS = [
    task("t1", "JOB-A", "設計レビュー", "09:00", "10:30"),
    task("t2", "JOB-B", "定例MTG", "10:30", "12:00"),
    task("t3", "JOB-A", "障害調査", "13:00", "16:30"),
    task("t4", "JOB-B", "資料作成", "16:30", "18:41"),
]
LUNCH = [brk("b1", "12:00", "13:00")]


def draft(**kwargs):  # type: ignore[no-untyped-def]
    params = {
        "work_date": WORK_DATE,
        "attendance": attendance(),
        "tasks": SPEC_TASKS,
        "breaks": LUNCH,
        "jobs": JOBS,
        "settings": DraftSettings(),
        "tz": TZ,
        "sales_items": SALES,
    }
    params.update(kwargs)
    return build_zac_draft(**params)


def codes(result) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return [(item.code, item.severity) for item in result.issues]


# ---- 仕様書 §4.6 の計算例 ----


def test_spec_example_duration() -> None:
    result = draft()

    assert result.attendance is not None
    assert (result.attendance.start, result.attendance.end, result.attendance.source) == ("09:02", "18:41", "hr_mail")
    assert [(b.start, b.end) for b in result.breaks] == [("12:00", "13:00")]
    assert result.working_minutes == 519
    assert [
        (e.work_kind, e.job_code, e.zac_search_text, e.project_name, e.sales_item, e.minutes, e.description)
        for e in result.entries
    ] == [
        (WORK, "JOB-A", "A社 保守", "A社保守", "保守（2026／10）", 300, "- 設計レビュー\n- 障害調査"),
        # zac 検索文字列が未設定ならジョブ ID
        (WORK, "JOB-B", "JOB-B", "社内業務", "社内業務", 210, "- 定例MTG\n- 資料作成"),
    ]
    assert codes(result) == [("TASK_OUTSIDE_ATTENDANCE", "warning")]
    assert result.issues[0].message == "09:00開始のタスクを出勤時刻09:02に切り詰めました"
    assert result.issues[0].ref_id == "t1"
    assert result.registrable is True
    assert result.auto_allowed is False


def test_clean_day_is_auto_allowed() -> None:
    result = draft(attendance=attendance("09:00", "18:41"))
    assert result.issues == []
    assert result.registrable is True
    assert result.auto_allowed is True


# ---- クリップ ----


def test_task_beyond_tolerance_is_error() -> None:
    tasks = [task("t1", "JOB-A", "", "09:00", "12:00"), task("t2", "JOB-A", "", "13:00", "18:30")]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)

    assert ("TASK_OUTSIDE_ATTENDANCE", "error") in codes(result)
    assert "18:30終了のタスクが退勤時刻18:00より30分後です" in [i.message for i in result.issues]
    assert result.registrable is False


def test_break_sticking_out_of_attendance_is_clipped() -> None:
    tasks = [task("t1", "JOB-A", "", "09:30", "18:00")]
    result = draft(
        attendance=attendance("09:00", "18:00"), tasks=tasks, breaks=[brk("b1", "08:30", "09:30")]
    )
    # 休憩は出退勤の範囲内の 09:00–09:30 だけを数える
    assert [(b.start, b.end) for b in result.breaks] == [("09:00", "09:30")]
    assert result.working_minutes == 510
    assert result.registrable is True


def test_times_after_midnight() -> None:
    tasks = [task("t1", "JOB-A", "夜間対応", "13:00", "01:30", end_day=10)]
    result = draft(
        attendance=attendance("12:00", "01:30", end_day=10),
        tasks=tasks,
        breaks=[brk("b1", "12:00", "13:00")],
    )
    assert result.attendance is not None
    assert result.attendance.end == "25:30"
    assert result.working_minutes == 750
    assert [e.minutes for e in result.entries] == [750]


# ---- 空き時間 ----


GAP_TASKS = [
    task("t1", "JOB-A", "", "09:00", "12:00"),
    task("t2", "JOB-A", "", "13:00", "15:00"),
    task("t3", "JOB-B", "", "15:20", "18:00"),
]


def test_gap_blocks_registration() -> None:
    result = draft(attendance=attendance("09:00", "18:00"), tasks=GAP_TASKS)

    assert ("UNCOVERED_TIME", "error") in codes(result)
    assert "15:00–15:20 がどのタスクにも休憩にも含まれていません" in [i.message for i in result.issues]
    # 配分が成立しなくても TOTAL_MISMATCH は重ねない（参考値を返す）
    assert ("TOTAL_MISMATCH", "error") not in codes(result)
    assert result.registrable is False


ASSIGN = DraftSettings(
    gap_policy="assign_default_job", default_job_code="JOB-B", default_work_kind="社内業務", default_sales_item_id="s-b"
)


def test_gap_assigned_to_default_job() -> None:
    result = draft(attendance=attendance("09:00", "18:00"), tasks=GAP_TASKS, settings=ASSIGN)

    assert codes(result) == [("UNCOVERED_TIME", "warning")]
    assert [(e.work_kind, e.job_code, e.minutes) for e in result.entries] == [
        (WORK, "JOB-A", 300),
        # 160 分と 20 分を最大剰余法で 15 分単位に（合計 480 分）
        (WORK, "JOB-B", 165),
        ("社内業務", "JOB-B", 15),
    ]
    assert result.registrable is True
    assert result.auto_allowed is False


def test_unknown_default_job_is_error() -> None:
    result = draft(
        attendance=attendance("09:00", "18:00"),
        tasks=GAP_TASKS,
        settings=DraftSettings(gap_policy="assign_default_job", default_job_code="NOPE"),
    )
    assert ("JOB_UNKNOWN", "error") in codes(result)
    assert ("WORK_KIND_MISSING", "error") in codes(result)
    assert ("SALES_ITEM_MISSING", "error") in codes(result)


# ---- 入力行 ----


@pytest.mark.parametrize(
    ("minutes", "target", "expected"),
    [
        ({"JOB-A": 298, "JOB-B": 221}, 510, {"JOB-A": 300, "JOB-B": 210}),
        # 剰余が同じなら分数の大きい順、次にジョブ ID 順
        ({"JOB-B": 37, "JOB-A": 37}, 75, {"JOB-A": 45, "JOB-B": 30}),
        ({"JOB-A": 38, "JOB-B": 52}, 90, {"JOB-A": 45, "JOB-B": 45}),
        ({"JOB-A": 30, "JOB-B": 30}, 60, {"JOB-A": 30, "JOB-B": 30}),
    ],
)
def test_largest_remainder(minutes: dict[str, int], target: int, expected: dict[str, int]) -> None:
    allocated = allocate_by_largest_remainder(minutes, target, 15)
    assert allocated == expected
    assert sum(allocated.values()) == target


def test_largest_remainder_reports_impossible_allocation() -> None:
    assert allocate_by_largest_remainder({"JOB-A": 30}, 90, 15) is None


def test_description_is_deduplicated_and_truncated() -> None:
    tasks = [
        task("t1", "JOB-A", "設計", "09:00", "12:00"),
        task("t2", "JOB-A", "設計", "13:00", "15:00"),
        task("t3", "JOB-A", "レビュー対応", "15:00", "18:00"),
    ]
    result = draft(
        attendance=attendance("09:00", "18:00"), tasks=tasks, settings=DraftSettings(description_max_length=5)
    )
    assert result.entries[0].description == "- 設計\n"


def test_time_range_merges_consecutive_rows() -> None:
    tasks = [
        task("t1", "JOB-A", "設計", "09:00", "10:30"),
        task("t2", "JOB-A", "設計", "10:30", "11:00"),
        task("t3", "JOB-B", "定例", "11:00", "12:00"),
        task("t4", "JOB-A", "設計", "13:00", "18:00"),
    ]
    result = draft(
        attendance=attendance("09:00", "18:00"), tasks=tasks, settings=DraftSettings(entry_style="time_range")
    )
    assert [(e.start, e.end, e.job_code, e.description, e.minutes) for e in result.entries] == [
        ("09:00", "11:00", "JOB-A", "- 設計", 120),
        ("11:00", "12:00", "JOB-B", "- 定例", 60),
        ("13:00", "18:00", "JOB-A", "- 設計", 300),
    ]


def test_different_work_kinds_make_separate_rows() -> None:
    tasks = [
        task("t1", "JOB-A", "設計", "09:00", "12:00"),
        task("t2", "JOB-A", "定例", "13:00", "14:00", work_kind="プロジェクト関連打ち合わせ"),
        task("t3", "JOB-A", "設計", "14:00", "18:00"),
    ]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)
    assert [(e.work_kind, e.minutes, e.description) for e in result.entries] == [
        (WORK, 420, "- 設計"),
        ("プロジェクト関連打ち合わせ", 60, "- 定例"),
    ]


def test_different_sales_items_make_separate_rows() -> None:
    tasks = [
        task("t1", "JOB-A", "", "09:00", "12:00"),
        task("t2", "JOB-A", "", "13:00", "18:00", sales_item="s-a9"),
    ]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)
    assert [e.sales_item for e in result.entries] == ["保守（2026／10）", "保守（2026／09）"]
    assert ("SALES_ITEM_MONTH_MISMATCH", "warning") in codes(result)
    assert result.registrable is True
    assert result.auto_allowed is False


# ---- 検証 ----


def test_missing_work_kind_and_sales_item() -> None:
    tasks = [
        task("t1", "JOB-A", "", "09:00", "12:00", work_kind=None),
        task("t2", "JOB-A", "", "13:00", "18:00", sales_item=None),
    ]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)
    assert [(i.code, i.ref_id) for i in result.issues] == [("WORK_KIND_MISSING", "t1"), ("SALES_ITEM_MISSING", "t2")]
    assert "09:00–12:00 のタスクに作業内容が設定されていません" == result.issues[0].message
    assert result.registrable is False


def test_job_month_mismatch() -> None:
    # 2026-10 の月次案件を 2026-11 の勤務日に使った
    result = draft(
        work_date=date(2026, 11, 9),
        attendance=AttendanceInput(
            datetime(2026, 11, 9, 9, 0, tzinfo=TZ), datetime(2026, 11, 9, 18, 0, tzinfo=TZ), "hr_mail", "work"
        ),
        tasks=[
            TaskInput("t1", "JOB-M", "", datetime(2026, 11, 9, 9, 0, tzinfo=TZ), datetime(2026, 11, 9, 12, 0, tzinfo=TZ), WORK, "s-m"),
            TaskInput("t2", "JOB-B", "", datetime(2026, 11, 9, 13, 0, tzinfo=TZ), datetime(2026, 11, 9, 18, 0, tzinfo=TZ), WORK, "s-b"),
        ],
        breaks=[BreakInput("b1", datetime(2026, 11, 9, 12, 0, tzinfo=TZ), datetime(2026, 11, 9, 13, 0, tzinfo=TZ))],
    )
    assert ("JOB_MONTH_MISMATCH", "error") in codes(result)
    assert "JOB-M は 2026-10 の案件です（勤務日は 2026-11）" in result.issues[0].message
    assert ("SALES_ITEM_MONTH_MISMATCH", "warning") in codes(result)
    assert result.registrable is False



def test_attendance_missing() -> None:
    result = draft(attendance=attendance(None, None))
    assert codes(result) == [("ATTENDANCE_MISSING", "error")]
    assert result.entries == []
    assert result.registrable is False


def test_on_leave_has_no_entries() -> None:
    result = draft(attendance=AttendanceInput(None, None, "manual", "leave"))
    assert codes(result) == [("ON_LEAVE", "error")]
    assert result.entries == []


def test_no_tasks() -> None:
    assert ("NO_TASKS", "error") in codes(draft(tasks=[]))


def test_running_task_and_break() -> None:
    result = draft(
        tasks=[*SPEC_TASKS[:3], task("t4", "JOB-B", "資料作成", "16:30", None)],
        breaks=[*LUNCH, brk("b2", "18:30", None)],
    )
    running = [i for i in result.issues if i.code == "TASK_RUNNING"]
    assert [i.ref_id for i in running] == ["t4", "b2"]


def test_task_overlapping_break_is_error() -> None:
    tasks = [task("t1", "JOB-A", "", "09:00", "12:30"), task("t2", "JOB-A", "", "13:00", "18:00")]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)
    overlap = [i for i in result.issues if i.code == "TASK_OVERLAP"]
    assert [(i.ref_id, i.message) for i in overlap] == [
        ("t1", "09:00–12:30 のタスクと 12:00–13:00 の休憩が重なっています")
    ]
    assert result.registrable is False


def test_unknown_job() -> None:
    tasks = [task("t1", "JOB-X", "", "09:00", "12:00", sales_item="s-a"), task("t2", "JOB-A", "", "13:00", "18:00")]
    result = draft(attendance=attendance("09:00", "18:00"), tasks=tasks)
    assert [(i.code, i.ref_id) for i in result.issues] == [("JOB_UNKNOWN", "t1")]


def test_break_missing_does_not_use_default_break() -> None:
    result = draft(attendance=attendance("08:29", "18:38"), breaks=[])
    assert ("BREAK_MISSING", "error") in codes(result)
    assert result.breaks == []
    assert result.registrable is False


def test_already_registered_is_info() -> None:
    registered = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)
    result = draft(attendance=attendance("09:00", "18:41"), zac_registered_at=registered)
    assert codes(result) == [("ALREADY_REGISTERED", "info")]
    assert result.registrable is True
    assert result.auto_allowed is True
    assert result.zac_registered_at == registered


# ---- API ----


def jst(hhmm: str, day: str = "2026-10-09") -> str:
    return f"{day}T{hhmm}:00+09:00"


def test_draft_api_matches_spec_example(client: TestClient) -> None:
    client.post("/api/zac-masters/import", json={
        "work_kinds": ["プロジェクト作業"],
        "projects": [
            {"code": "JOB-A", "name": "A社保守", "sales_items": [{"name": "保守（2026／10）"}]},
            {"code": "JOB-B", "name": "社内業務", "sales_items": [{"name": "社内業務"}]},
        ],
    })
    client.patch("/api/jobs/JOB-A", json={"zac_search_text": "A社 保守"})
    item_ids = {item["job_code"]: item["id"] for item in client.get("/api/zac-sales-items").json()}
    day = "2026-10-09"
    # 出退勤を先に登録する（登録時の時刻合わせを通さず、仕様書の例の切り詰めを再現する）
    client.put(
        f"/api/work-reports/{day}/attendance",
        json={"start_at": jst("09:02"), "end_at": jst("18:41"), "source": "hr_mail", "kind": "work"},
    )
    for job, description, start, end in [
        ("JOB-A", "設計レビュー", "09:00", "10:30"),
        ("JOB-B", "定例MTG", "10:30", "12:00"),
        ("JOB-A", "障害調査", "13:00", "16:30"),
        ("JOB-B", "資料作成", "16:30", "18:41"),
    ]:
        client.post(
            f"/api/work-reports/{day}/tasks",
            json={
                "job_code": job,
                "description": description,
                "work_kind": "プロジェクト作業",
                "sales_item_id": item_ids[job],
                "start_at": jst(start),
                "end_at": jst(end),
            },
        )
    client.post(f"/api/work-reports/{day}/breaks", json={"start_at": jst("12:00"), "end_at": jst("13:00")})
    before = client.get(f"/api/work-reports/{day}").json()

    response = client.get(f"/api/work-reports/{day}/zac-draft")

    assert response.status_code == 200
    body = response.json()
    assert body["working_minutes"] == 519
    assert [(e["job_code"], e["sales_item"], e["minutes"]) for e in body["entries"]] == [
        ("JOB-A", "保守（2026／10）", 300),
        ("JOB-B", "社内業務", 210),
    ]
    assert body["entries"][0]["description"] == "- 設計レビュー\n- 障害調査"
    assert body["entry_style"] == "duration"
    assert body["registrable"] is True
    assert body["auto_allowed"] is False
    assert body["zac_registered_at"] is None
    assert client.get(f"/api/work-reports/{day}").json()["updated_at"] == before["updated_at"]


def test_draft_api_does_not_create_report_or_settings(client: TestClient) -> None:
    response = client.get("/api/work-reports/2026-10-08/zac-draft")

    assert response.status_code == 200
    assert [i["code"] for i in response.json()["issues"]] == ["ATTENDANCE_MISSING"]
    assert client.get("/api/work-reports", params={"year": 2026, "month": 10}).json() == []

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import repositories

WORK_DATE = "2026-10-09"


def jst(hhmm: str, day: str = WORK_DATE) -> str:
    return f"{day}T{hhmm}:00+09:00"


def as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


@pytest.fixture()
def set_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def apply(value: str) -> None:
        monkeypatch.setattr(repositories, "now_utc", lambda: as_utc(value))

    return apply


@pytest.fixture()
def jobs(client: TestClient) -> None:
    for code, name in [("JOB-A", "A社保守"), ("JOB-B", "社内業務")]:
        assert client.post("/api/jobs", json={"code": code, "name": name}).status_code == 201


def add_task(
    client: TestClient,
    start: str,
    end: str | None,
    job: str = "JOB-A",
    description: str = "",
    day: str = WORK_DATE,
):
    return client.post(
        f"/api/work-reports/{day}/tasks",
        json={
            "job_code": job,
            "description": description,
            "start_at": start,
            "end_at": end,
        },
    )


def add_break(client: TestClient, start: str, end: str | None, day: str = WORK_DATE):
    return client.post(
        f"/api/work-reports/{day}/breaks", json={"start_at": start, "end_at": end}
    )


# ---- ジョブマスタ ----


def test_create_job_and_reject_duplicate(client: TestClient) -> None:
    created = client.post(
        "/api/jobs",
        json={"code": "JOB-A", "name": "A社保守", "zac_search_text": "A社 保守"},
    )
    assert created.status_code == 201
    assert created.json()["is_active"] is True
    assert created.json()["zac_search_text"] == "A社 保守"

    duplicate = client.post("/api/jobs", json={"code": "JOB-A", "name": "別名"})
    assert duplicate.status_code == 409

    jobs = client.get("/api/jobs").json()
    assert [job["name"] for job in jobs] == ["A社保守"]


def test_jobs_search_order_and_inactive_filter(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    client.post("/api/jobs", json={"code": "OTHER-1", "name": "その他"})

    # 未使用は code 順
    assert [j["code"] for j in client.get("/api/jobs").json()] == [
        "JOB-A",
        "JOB-B",
        "OTHER-1",
    ]

    set_now(jst("10:00"))
    assert add_task(client, jst("09:00"), jst("10:00"), job="JOB-A").status_code == 201
    set_now(jst("10:30"))
    started = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start", json={"job_code": "JOB-B"}
    )
    assert started.status_code == 201

    # 最近使った順（JOB-B → JOB-A → 未使用）
    assert [j["code"] for j in client.get("/api/jobs").json()] == [
        "JOB-B",
        "JOB-A",
        "OTHER-1",
    ]

    # 部分一致検索（ID・表示名）
    assert [j["code"] for j in client.get("/api/jobs", params={"q": "job"}).json()] == [
        "JOB-B",
        "JOB-A",
    ]
    assert [j["code"] for j in client.get("/api/jobs", params={"q": "社内"}).json()] == [
        "JOB-B"
    ]

    # 無効化すると active=true の候補から外れるが、既存タスクには影響しない
    disabled = client.patch("/api/jobs/JOB-A", json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    active_codes = [
        j["code"] for j in client.get("/api/jobs", params={"active": "true"}).json()
    ]
    assert "JOB-A" not in active_codes
    tasks = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert tasks[0]["job_code"] == "JOB-A"

    assert client.patch("/api/jobs/NOPE", json={"name": "x"}).status_code == 404


def test_change_job_code_creates_new_job_and_disables_old(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    client.post(
        "/api/jobs",
        json={"code": "JOB-2610", "name": "A社保守", "zac_search_text": "A社 保守", "zac_work_category": "保守"},
    )
    set_now(jst("10:00"))
    task = add_task(client, jst("09:00"), jst("10:00"), job="JOB-2610").json()

    response = client.post(
        "/api/jobs/JOB-2610/change-code", json={"code": " JOB-2611 ", "name": "A社保守（11月）"}
    )

    assert response.status_code == 201
    created = response.json()
    assert created["code"] == "JOB-2611"
    assert created["name"] == "A社保守（11月）"
    # 指定のない項目は元のジョブから引き継ぐ
    assert created["zac_search_text"] == "A社 保守"
    assert created["zac_work_category"] == "保守"
    assert created["is_active"] is True
    assert created["last_used_at"] is not None

    jobs = {j["code"]: j for j in client.get("/api/jobs").json()}
    assert jobs["JOB-2610"]["is_active"] is False
    assert jobs["JOB-2610"]["name"] == "A社保守"
    # 記録済みのタスクは元の ID のまま
    tasks = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert [(t["id"], t["job_code"]) for t in tasks] == [(task["id"], "JOB-2610")]


def test_change_job_code_rejects_existing_code(client: TestClient, jobs: None) -> None:
    response = client.post("/api/jobs/JOB-A/change-code", json={"code": "JOB-B"})

    assert response.status_code == 409
    jobs_by_code = {j["code"]: j for j in client.get("/api/jobs").json()}
    assert jobs_by_code["JOB-A"]["is_active"] is True
    assert jobs_by_code["JOB-B"]["name"] == "社内業務"


@pytest.mark.parametrize("code", ["", "   ", "JOB-A"])
def test_change_job_code_rejects_empty_or_same_code(
    client: TestClient, jobs: None, code: str
) -> None:
    assert client.post("/api/jobs/JOB-A/change-code", json={"code": code}).status_code == 422
    assert client.get("/api/jobs", params={"active": "true"}).json()[0]["code"] == "JOB-A"


def test_change_job_code_unknown_job(client: TestClient) -> None:
    assert client.post("/api/jobs/NOPE/change-code", json={"code": "JOB-X"}).status_code == 404


# ---- 検証・重なり ----


def test_adjacent_tasks_are_allowed(client: TestClient, jobs: None) -> None:
    assert add_task(client, jst("09:00"), jst("10:30")).status_code == 201
    assert add_task(client, jst("10:30"), jst("12:00"), job="JOB-B").status_code == 201


def test_overlapping_tasks_are_saved(client: TestClient, jobs: None) -> None:
    # 重なりは保存時に拒否しない（利用者が後で調整する。zac 登録前のドラフトで検出する）
    add_task(client, jst("13:00"), jst("14:00"))

    response = add_task(client, jst("13:30"), jst("15:00"), job="JOB-B")

    assert response.status_code == 201
    assert len(client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()) == 2


def test_task_overlapping_break_is_saved(client: TestClient, jobs: None) -> None:
    add_break(client, jst("12:00"), jst("13:00"))

    assert add_task(client, jst("11:30"), jst("12:30")).status_code == 201


def test_break_overlapping_task_is_saved(client: TestClient, jobs: None) -> None:
    add_task(client, jst("11:00"), jst("12:30"))

    assert add_break(client, jst("12:00"), jst("13:00")).status_code == 201
    assert len(client.get(f"/api/work-reports/{WORK_DATE}/breaks").json()) == 1


def test_entry_overlapping_running_task_is_saved(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("11:00"))
    assert add_task(client, jst("09:00"), None).status_code == 201

    assert add_break(client, jst("10:30"), jst("10:45")).status_code == 201


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (jst("23:59", "2026-10-08"), jst("09:00")),  # 勤務日の 00:00 より前
        (jst("05:00", "2026-10-10"), jst("06:00", "2026-10-10")),  # 翌 06:00 以降
    ],
)
def test_out_of_range_times_are_rejected(
    client: TestClient, jobs: None, start: str, end: str
) -> None:
    response = add_task(client, start, end)

    assert response.status_code == 422
    assert client.get(f"/api/work-reports/{WORK_DATE}/tasks").json() == []


def test_end_must_be_after_start(client: TestClient, jobs: None) -> None:
    assert add_task(client, jst("10:00"), jst("09:30")).status_code == 422
    assert add_task(client, jst("10:00"), jst("10:00")).status_code == 422
    assert add_break(client, jst("13:00"), jst("12:00")).status_code == 422


def test_description_length_and_unknown_job(client: TestClient, jobs: None) -> None:
    assert add_task(client, jst("09:00"), jst("10:00"), description="あ" * 200).status_code == 201
    assert (
        add_task(client, jst("10:00"), jst("11:00"), description="あ" * 201).status_code
        == 422
    )
    assert add_task(client, jst("10:00"), jst("11:00"), job="JOB-C").status_code == 422


def test_naive_datetime_is_rejected(client: TestClient, jobs: None) -> None:
    response = add_task(client, f"{WORK_DATE}T09:00:00", f"{WORK_DATE}T10:00:00")
    assert response.status_code == 422


# ---- タスク CRUD ----


def test_task_crud_and_start_order(client: TestClient, jobs: None) -> None:
    later = add_task(client, jst("13:00"), jst("16:30"), description="障害調査").json()
    earlier = add_task(
        client, jst("09:00"), jst("10:30"), description="設計レビュー"
    ).json()

    listed = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert [t["id"] for t in listed] == [earlier["id"], later["id"]]
    assert listed[0]["description"] == "設計レビュー"
    assert listed[0]["job_code"] == "JOB-A"

    updated = client.patch(
        f"/api/tasks/{later['id']}",
        json={"job_code": "JOB-B", "description": "資料作成", "end_at": jst("17:00")},
    )
    assert updated.status_code == 200
    assert updated.json()["job_code"] == "JOB-B"
    assert updated.json()["description"] == "資料作成"
    assert as_utc(updated.json()["end_at"]) == as_utc(jst("17:00"))

    # 編集で重なっても保存する
    overlap = client.patch(f"/api/tasks/{later['id']}", json={"start_at": jst("10:00")})
    assert overlap.status_code == 200
    assert as_utc(overlap.json()["start_at"]) == as_utc(jst("10:00"))

    assert client.delete(f"/api/tasks/{earlier['id']}").status_code == 204
    remaining = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert [t["id"] for t in remaining] == [later["id"]]
    assert client.delete(f"/api/tasks/{earlier['id']}").status_code == 404


def test_task_list_for_day_without_report_is_empty(client: TestClient) -> None:
    assert client.get("/api/work-reports/2026-10-01/tasks").json() == []
    assert client.get("/api/work-reports/2026-10-01/breaks").json() == []


def test_task_ending_after_midnight_is_saved(client: TestClient, jobs: None) -> None:
    # 25:15 相当（翌日 01:15 JST）
    response = add_task(client, jst("23:00"), jst("01:15", "2026-10-10"))

    assert response.status_code == 201
    assert as_utc(response.json()["end_at"]) == datetime(2026, 10, 9, 16, 15, tzinfo=UTC)


def test_second_running_task_is_rejected(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("12:00"))
    running = add_task(client, jst("11:00"), None).json()

    response = add_task(client, jst("09:00"), None, job="JOB-B")

    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"][0]["id"] == running["id"]


# ---- 開始・停止 ----


def test_start_switches_running_task_at_same_time(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("09:00"))
    first = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start",
        json={"job_code": "JOB-A", "description": "設計レビュー"},
    )
    assert first.status_code == 201
    assert first.json()["end_at"] is None

    set_now(jst("10:30"))
    second = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start",
        json={"job_code": "JOB-B", "description": "定例MTG"},
    )
    assert second.status_code == 201

    tasks = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert [t["job_code"] for t in tasks] == ["JOB-A", "JOB-B"]
    assert as_utc(tasks[0]["end_at"]) == as_utc(jst("10:30"))
    assert as_utc(tasks[1]["start_at"]) == as_utc(jst("10:30"))
    assert tasks[1]["end_at"] is None

    set_now(jst("12:00"))
    stopped = client.post(f"/api/tasks/{second.json()['id']}/stop")
    assert stopped.status_code == 200
    assert as_utc(stopped.json()["end_at"]) == as_utc(jst("12:00"))
    assert client.post(f"/api/tasks/{second.json()['id']}/stop").status_code == 409


def test_start_outside_work_day_is_rejected(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("09:00", "2026-10-13"))
    response = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start", json={"job_code": "JOB-A"}
    )
    assert response.status_code == 422


# ---- 休憩 ----


def test_break_start_stops_running_task_and_resume(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("09:00"))
    client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start",
        json={"job_code": "JOB-A", "description": "設計レビュー"},
    )

    set_now(jst("12:00"))
    started = client.post(f"/api/work-reports/{WORK_DATE}/breaks/start")
    assert started.status_code == 201
    assert started.json()["source"] == "manual"
    assert started.json()["end_at"] is None

    tasks = client.get(f"/api/work-reports/{WORK_DATE}/tasks").json()
    assert as_utc(tasks[0]["end_at"]) == as_utc(jst("12:00"))

    set_now(jst("13:00"))
    stopped = client.post(f"/api/breaks/{started.json()['id']}/stop")
    assert stopped.status_code == 200
    assert as_utc(stopped.json()["end_at"]) == as_utc(jst("13:00"))

    resumed = client.post(
        f"/api/work-reports/{WORK_DATE}/tasks/start",
        json={"job_code": "JOB-A", "description": "設計レビュー"},
    )
    assert resumed.status_code == 201
    assert as_utc(resumed.json()["start_at"]) == as_utc(jst("13:00"))


def test_task_start_ends_running_break(
    client: TestClient, jobs: None, set_now: Callable[[str], None]
) -> None:
    set_now(jst("12:00"))
    client.post(f"/api/work-reports/{WORK_DATE}/breaks/start")
    set_now(jst("12:45"))
    client.post(f"/api/work-reports/{WORK_DATE}/tasks/start", json={"job_code": "JOB-A"})

    breaks = client.get(f"/api/work-reports/{WORK_DATE}/breaks").json()
    assert as_utc(breaks[0]["end_at"]) == as_utc(jst("12:45"))


def test_second_running_break_is_rejected(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now(jst("12:30"))
    running = add_break(client, jst("12:00"), None).json()

    response = add_break(client, jst("10:00"), None)

    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"][0]["id"] == running["id"]


def test_break_crud(client: TestClient) -> None:
    created = add_break(client, jst("12:00"), jst("13:00"))
    assert created.status_code == 201
    assert created.json()["source"] == "manual"

    break_id = created.json()["id"]
    updated = client.patch(
        f"/api/breaks/{break_id}", json={"start_at": jst("11:45"), "end_at": jst("12:45")}
    )
    assert updated.status_code == 200
    assert as_utc(updated.json()["start_at"]) == as_utc(jst("11:45"))

    assert client.delete(f"/api/breaks/{break_id}").status_code == 204
    assert client.get(f"/api/work-reports/{WORK_DATE}/breaks").json() == []


# ---- 自動化設定 ----


def test_automation_settings_default_and_update(client: TestClient) -> None:
    initial = client.get("/api/automation-settings")
    assert initial.status_code == 200
    assert initial.json()["default_break_start"] == "12:00"
    assert initial.json()["default_break_end"] == "13:00"

    saved = client.put(
        "/api/automation-settings",
        json={"default_break_start": "11:45", "default_break_end": "12:45"},
    )
    assert saved.status_code == 200
    assert client.get("/api/automation-settings").json()["default_break_start"] == "11:45"


@pytest.mark.parametrize(
    ("start", "end"),
    [("12:0", "13:00"), ("12:00", "1300"), ("12:60", "13:00"), ("13:00", "12:00")],
)
def test_automation_settings_validation(
    client: TestClient, start: str, end: str
) -> None:
    response = client.put(
        "/api/automation-settings",
        json={"default_break_start": start, "default_break_end": end},
    )
    assert response.status_code == 422


# ---- zac 連携の設定 ----


def test_zac_settings_defaults(client: TestClient) -> None:
    settings = client.get("/api/automation-settings").json()
    assert {
        key: settings[key]
        for key in (
            "zac_submit_mode",
            "entry_style",
            "time_unit_minutes",
            "clip_tolerance_minutes",
            "gap_policy",
            "default_job_code",
            "description_max_length",
        )
    } == {
        "zac_submit_mode": "dry_run",
        "entry_style": "duration",
        "time_unit_minutes": 15,
        "clip_tolerance_minutes": 15,
        "gap_policy": "block",
        "default_job_code": None,
        "description_max_length": 100,
    }


def zac_settings(**overrides: object) -> dict[str, object]:
    return {"default_break_start": "12:00", "default_break_end": "13:00", **overrides}


def test_zac_settings_save_and_reload(client: TestClient, jobs: None) -> None:
    client.post("/api/zac-work-kinds", json={"name": "社内業務"})
    item = client.post("/api/jobs/JOB-B/sales-items", json={"name": "事務作業等"}).json()
    saved = client.put(
        "/api/automation-settings",
        json=zac_settings(
            zac_submit_mode="assist",
            entry_style="time_range",
            time_unit_minutes=30,
            clip_tolerance_minutes=10,
            gap_policy="assign_default_job",
            default_job_code="JOB-B",
            default_work_kind="社内業務",
            default_sales_item_id=item["id"],
            description_max_length=50,
        ),
    )
    assert saved.status_code == 200
    current = client.get("/api/automation-settings").json()
    assert current["gap_policy"] == "assign_default_job"
    assert current["default_job_code"] == "JOB-B"
    assert current["default_work_kind"] == "社内業務"
    assert current["default_sales_item_id"] == item["id"]
    assert current["time_unit_minutes"] == 30


@pytest.mark.parametrize(
    "overrides",
    [
        {"gap_policy": "assign_default_job"},
        {"gap_policy": "assign_default_job", "default_job_code": " "},
        {"gap_policy": "assign_default_job", "default_job_code": "JOB-B"},
        {"default_work_kind": "NOPE"},
        {"default_job_code": "NOPE"},
        {"time_unit_minutes": 7},
        {"time_unit_minutes": 0},
        {"time_unit_minutes": 90},
        {"zac_submit_mode": "submit"},
        {"entry_style": "minutes"},
        {"clip_tolerance_minutes": -1},
        {"description_max_length": 0},
    ],
)
def test_zac_settings_validation(
    client: TestClient, jobs: None, overrides: dict[str, object]
) -> None:
    assert client.put("/api/automation-settings", json=zac_settings(**overrides)).status_code == 422
    assert client.get("/api/automation-settings").json()["gap_policy"] == "block"

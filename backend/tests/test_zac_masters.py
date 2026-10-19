from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

DAY = "2026-10-09"
SEED = Path(__file__).resolve().parents[1] / "seed" / "zac_masters_2026-10-14.json"


def jst(hhmm: str) -> str:
    return f"{DAY}T{hhmm}:00+09:00"


def import_masters(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/zac-masters/import", json=payload)
    assert response.status_code == 200
    return response.json()


SAMPLE = {
    "work_kinds": ["プロジェクト作業", "プロジェクト関連打ち合わせ"],
    "projects": [
        {
            "code": "2602028",
            "name": "エンジンファーム様プロジェクトサポート（2026／09-2026／12）",
            "sales_items": [
                {"name": "プロジェクトサポート（2026／09）", "is_closed": True},
                {"name": "プロジェクトサポート（2026／10）"},
            ],
        },
        {"code": "2602062", "name": "bizoceanAPPs開発(26/10)", "sales_items": [{"name": "bizoceanAPPs開発(26/10)"}]},
        {
            "code": "2600901",
            "name": "第26期 Ｒ＆Ｄ戦略室 社内管理業務",
            "sales_items": [{"name": "社内管理業務"}, {"name": "外部研修"}],
        },
    ],
}


# ---- 取込 ----


def test_import_creates_masters_with_series_and_months(client: TestClient) -> None:
    result = import_masters(client, SAMPLE)
    assert result["created"] == {"work_kinds": 2, "jobs": 3, "sales_items": 5}
    assert result["missing_jobs"] == []

    jobs = {job["code"]: job for job in client.get("/api/jobs").json()}
    assert (jobs["2602062"]["series_name"], jobs["2602062"]["valid_month"]) == ("bizoceanAPPs開発", "2026-10")
    # 期間は対象年月なし
    assert (jobs["2602028"]["series_name"], jobs["2602028"]["valid_month"]) == (None, None)
    assert jobs["2600901"]["valid_month"] is None

    items = client.get("/api/zac-sales-items", params={"job_code": "2602028"}).json()
    assert [(i["name"], i["valid_month"], i["is_closed"]) for i in items] == [
        ("プロジェクトサポート（2026／09）", "2026-09", True),
        ("プロジェクトサポート（2026／10）", "2026-10", False),
    ]
    kinds = client.get("/api/zac-work-kinds").json()
    assert [k["name"] for k in kinds] == ["プロジェクト作業", "プロジェクト関連打ち合わせ"]


def test_import_is_idempotent_and_never_disables(client: TestClient) -> None:
    import_masters(client, SAMPLE)
    again = import_masters(client, SAMPLE)
    assert again["created"] == {"work_kinds": 0, "jobs": 0, "sales_items": 0}
    assert again["updated"] == {"work_kinds": 0, "jobs": 0, "sales_items": 0}

    # 翌月の案件だけが候補に出た
    result = import_masters(
        client,
        {
            "work_kinds": [],
            "projects": [
                {"code": "2602063", "name": "bizoceanAPPs開発(26/11)", "sales_items": [{"name": "bizoceanAPPs開発(26/11)"}]}
            ],
        },
    )
    assert result["created"]["jobs"] == 1
    assert result["missing_jobs"] == ["2600901", "2602028", "2602062"]
    jobs = {job["code"]: job for job in client.get("/api/jobs").json()}
    assert all(job["is_active"] for job in jobs.values())
    assert (jobs["2602063"]["series_name"], jobs["2602063"]["valid_month"]) == ("bizoceanAPPs開発", "2026-11")


def test_import_updates_closed_flag(client: TestClient) -> None:
    import_masters(client, SAMPLE)
    changed = json.loads(json.dumps(SAMPLE))
    changed["projects"][0]["sales_items"][1]["is_closed"] = True
    result = import_masters(client, changed)
    assert result["updated"]["sales_items"] == 1
    items = client.get("/api/zac-sales-items", params={"job_code": "2602028"}).json()
    assert [i["is_closed"] for i in items] == [True, True]


def test_seed_file_imports(client: TestClient) -> None:
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    projects = [
        {"code": code, "name": project["name"], "sales_items": [{"name": name} for name in project["sales_items"]]}
        for code, project in payload["projects"].items()
    ]
    result = import_masters(client, {"work_kinds": payload["work_kinds"], "projects": projects})
    assert result["created"]["work_kinds"] == 26
    assert result["created"]["jobs"] == 5


# ---- 作業内容・売上項目の CRUD ----


def test_work_kind_crud(client: TestClient) -> None:
    assert client.post("/api/zac-work-kinds", json={"name": " 研修等 "}).status_code == 201
    assert client.post("/api/zac-work-kinds", json={"name": "研修等"}).status_code == 409
    assert client.patch("/api/zac-work-kinds/研修等", json={"is_active": False}).json()["is_active"] is False
    assert client.get("/api/zac-work-kinds", params={"active": "true"}).json() == []
    assert client.patch("/api/zac-work-kinds/NOPE", json={"is_active": False}).status_code == 404


def test_sales_item_crud(client: TestClient) -> None:
    client.post("/api/jobs", json={"code": "2602028", "name": "エンジンファーム様"})
    created = client.post("/api/jobs/2602028/sales-items", json={"name": "プロジェクトサポート（2026／11）"})
    assert created.status_code == 201
    assert created.json()["valid_month"] == "2026-11"
    assert client.post("/api/jobs/2602028/sales-items", json={"name": "プロジェクトサポート（2026／11）"}).status_code == 409
    assert client.post("/api/jobs/NOPE/sales-items", json={"name": "x"}).status_code == 404
    patched = client.patch(f"/api/zac-sales-items/{created.json()['id']}", json={"is_active": False, "is_closed": True})
    assert (patched.json()["is_active"], patched.json()["is_closed"]) == (False, True)


def test_job_created_by_hand_derives_series(client: TestClient) -> None:
    created = client.post("/api/jobs", json={"code": "2602063", "name": "bizoceanAPPs開発(26/11)"}).json()
    assert (created["series_name"], created["valid_month"]) == ("bizoceanAPPs開発", "2026-11")
    cleared = client.patch("/api/jobs/2602063", json={"series_name": "", "valid_month": None}).json()
    assert (cleared["series_name"], cleared["valid_month"]) == (None, None)
    assert client.patch("/api/jobs/2602063", json={"valid_month": "2026-13"}).status_code == 422


# ---- タスクの作業内容・売上項目 ----


@pytest.fixture()
def masters(client: TestClient) -> dict[str, str]:
    import_masters(client, SAMPLE)
    items = {i["name"]: i["id"] for i in client.get("/api/zac-sales-items").json()}
    return items


def add_task(client: TestClient, **fields: Any):
    payload = {"job_code": "2600901", "description": "", "start_at": jst("09:00"), "end_at": jst("10:00"), **fields}
    return client.post(f"/api/work-reports/{DAY}/tasks", json=payload)


def test_task_with_work_kind_and_sales_item(client: TestClient, masters: dict[str, str]) -> None:
    response = add_task(client, work_kind="プロジェクト作業", sales_item_id=masters["外部研修"])
    assert response.status_code == 201
    body = response.json()
    assert (body["work_kind"], body["sales_item_id"]) == ("プロジェクト作業", masters["外部研修"])
    listed = client.get(f"/api/work-reports/{DAY}/tasks").json()
    assert listed[0]["sales_item_id"] == masters["外部研修"]


def test_task_without_zac_attributes_is_allowed(client: TestClient, masters: dict[str, str]) -> None:
    body = add_task(client).json()
    assert (body["work_kind"], body["sales_item_id"]) == (None, None)


@pytest.mark.parametrize(
    "fields",
    [
        {"sales_item_id": "PLACEHOLDER_OTHER_JOB"},
        {"sales_item_id": "missing"},
        {"work_kind": "存在しない作業内容"},
    ],
)
def test_task_rejects_invalid_zac_attributes(
    client: TestClient, masters: dict[str, str], fields: dict[str, str]
) -> None:
    if fields.get("sales_item_id") == "PLACEHOLDER_OTHER_JOB":
        fields = {"sales_item_id": masters["プロジェクトサポート（2026／10）"]}
    assert add_task(client, **fields).status_code == 422
    assert client.get(f"/api/work-reports/{DAY}/tasks").json() == []


def test_changing_job_drops_sales_item_of_old_job(client: TestClient, masters: dict[str, str]) -> None:
    task = add_task(client, sales_item_id=masters["外部研修"]).json()
    moved = client.patch(f"/api/tasks/{task['id']}", json={"job_code": "2602062"})
    assert moved.status_code == 200
    assert moved.json()["sales_item_id"] is None

    updated = client.patch(
        f"/api/tasks/{task['id']}",
        json={"sales_item_id": masters["bizoceanAPPs開発(26/10)"], "work_kind": "プロジェクト関連打ち合わせ"},
    ).json()
    assert updated["sales_item_id"] == masters["bizoceanAPPs開発(26/10)"]
    assert updated["work_kind"] == "プロジェクト関連打ち合わせ"
    cleared = client.patch(f"/api/tasks/{task['id']}", json={"work_kind": None}).json()
    assert cleared["work_kind"] is None


def test_task_defaults_use_latest_values_per_job(client: TestClient, masters: dict[str, str]) -> None:
    add_task(client, work_kind="プロジェクト作業", sales_item_id=masters["社内管理業務"])
    later = {"start_at": f"{DAY}T13:00:00+09:00", "end_at": f"{DAY}T14:00:00+09:00"}
    add_task(client, work_kind="プロジェクト関連打ち合わせ", **later)
    add_task(client, job_code="2602062", start_at=f"{DAY}T15:00:00+09:00", end_at=f"{DAY}T16:00:00+09:00")

    defaults = client.get("/api/zac-task-defaults").json()
    # 作業内容は直近の値、売上項目は直近の非 null の値
    assert defaults == [
        {"job_code": "2600901", "work_kind": "プロジェクト関連打ち合わせ", "sales_item_id": masters["社内管理業務"]}
    ]


def test_import_skips_projects_of_past_months(client: TestClient) -> None:
    payload = {
        "as_of_month": "2026-10",
        "work_kinds": [],
        "projects": [
            {"code": "2602061", "name": "bizoceanAPPs開発(26/09)", "sales_items": [{"name": "bizoceanAPPs開発(26/09)"}]},
            {"code": "2600733", "name": "第26期 XDG運営業務(26/08)", "sales_items": []},
            {"code": "2602062", "name": "bizoceanAPPs開発(26/10)", "sales_items": [{"name": "bizoceanAPPs開発(26/10)"}]},
            # 期間・年月なしの案件は取り込む
            {"code": "2602028", "name": "エンジンファーム様（2026／09-2026／12）", "sales_items": []},
            {"code": "2601570", "name": "サービス開発本部 make.AI 業務", "sales_items": []},
        ],
    }
    result = import_masters(client, payload)
    assert result["skipped_jobs"] == ["2602061", "2600733"]
    assert sorted(job["code"] for job in client.get("/api/jobs").json()) == ["2601570", "2602028", "2602062"]
    assert [i["job_code"] for i in client.get("/api/zac-sales-items").json()] == ["2602062"]


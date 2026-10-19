from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import repositories

DAY = "2026-10-09"


def as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


@pytest.fixture()
def set_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def apply(value: str) -> None:
        monkeypatch.setattr(repositories, "now_utc", lambda: as_utc(value))

    return apply


def start_run(client: TestClient, day: str = DAY, mode: str = "dry_run") -> dict:
    response = client.post(
        "/api/zac-sync-runs", json={"work_date": day, "mode": mode, "agent_version": "0.1.0"}
    )
    assert response.status_code == 201
    return response.json()


def finish_run(client: TestClient, run_id: str, status: str, **extra: object):
    return client.patch(f"/api/zac-sync-runs/{run_id}", json={"status": status, **extra})


# ---- 実行履歴 ----


def test_run_records_result_and_succeeded_sets_registered_at(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now("2026-10-13T09:20:00+09:00")
    run = start_run(client)
    assert run["status"] == "running"
    assert run["finished_at"] is None

    set_now("2026-10-13T09:22:00+09:00")
    entries = [{"job_code": "JOB-A", "minutes": 300}]
    updated = finish_run(client, run["id"], "succeeded", entries=entries, screenshot_path="/tmp/x.png")

    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "succeeded"
    assert body["entries"] == entries
    assert as_utc(body["finished_at"]) == as_utc("2026-10-13T09:22:00+09:00")
    report = client.get(f"/api/work-reports/{DAY}").json()
    assert as_utc(report["zac_registered_at"]) == as_utc("2026-10-13T09:22:00+09:00")
    assert report["zac_status"] == "registered"


def test_non_success_does_not_set_registered_at(client: TestClient) -> None:
    run = start_run(client)
    finish_run(client, run["id"], "dry_run_done")
    assert client.get(f"/api/work-reports/{DAY}").json()["zac_registered_at"] is None


def test_runs_are_filtered_by_date_and_newest_first(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now("2026-10-13T09:20:00+09:00")
    first = start_run(client)
    set_now("2026-10-13T10:20:00+09:00")
    second = start_run(client)
    start_run(client, day="2026-10-08")

    runs = client.get("/api/zac-sync-runs", params={"work_date": DAY}).json()
    assert [run["id"] for run in runs] == [second["id"], first["id"]]


@pytest.mark.parametrize("status", ["requested", "cancelled", "bogus"])
def test_patch_rejects_request_states(client: TestClient, status: str) -> None:
    run = start_run(client)
    assert finish_run(client, run["id"], status).status_code == 422


def test_patch_unknown_run(client: TestClient) -> None:
    assert finish_run(client, "nope", "failed").status_code == 404


# ---- 画面からの実行依頼 ----


def test_request_claim_and_finish(client: TestClient, set_now: Callable[[str], None]) -> None:
    client.put(
        "/api/automation-settings",
        json={"default_break_start": "12:00", "default_break_end": "13:00", "zac_submit_mode": "assist"},
    )
    set_now("2026-10-13T09:00:00+09:00")
    requested = client.post("/api/zac-sync-runs/requests", json={"work_date": DAY})
    assert requested.status_code == 201
    run = requested.json()
    assert (run["status"], run["mode"]) == ("requested", "assist")

    pending = client.get("/api/zac-sync-runs", params={"status": "requested", "order": "asc"}).json()
    assert [item["id"] for item in pending] == [run["id"]]

    set_now("2026-10-13T09:01:00+09:00")
    claimed = client.post(f"/api/zac-sync-runs/{run['id']}/claim")
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "running"
    assert as_utc(claimed.json()["started_at"]) == as_utc("2026-10-13T09:01:00+09:00")

    # 2 回目の取得は失敗する（二重実行の防止）
    assert client.post(f"/api/zac-sync-runs/{run['id']}/claim").status_code == 409

    assert finish_run(client, run["id"], "dry_run_done").json()["status"] == "dry_run_done"


def test_duplicate_request_is_rejected(client: TestClient, set_now: Callable[[str], None]) -> None:
    set_now("2026-10-13T09:00:00+09:00")
    assert client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).status_code == 201
    duplicate = client.post("/api/zac-sync-runs/requests", json={"work_date": DAY})
    assert duplicate.status_code == 409
    assert "依頼中" in duplicate.json()["detail"]["message"]
    # 別の日は依頼できる
    assert client.post("/api/zac-sync-runs/requests", json={"work_date": "2026-10-08"}).status_code == 201


def test_request_is_rejected_while_running_but_not_when_stale(
    client: TestClient, set_now: Callable[[str], None]
) -> None:
    set_now("2026-10-13T09:00:00+09:00")
    start_run(client)
    assert client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).status_code == 409

    # 実行中のまま 60 分以上たった記録は、新しい依頼を塞がない
    set_now("2026-10-13T10:01:00+09:00")
    assert client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).status_code == 201


def test_cancel_request(client: TestClient) -> None:
    run = client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).json()

    cancelled = client.post(f"/api/zac-sync-runs/{run['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None
    # 取り消した依頼は取得できず、もう一度依頼できる
    assert client.post(f"/api/zac-sync-runs/{run['id']}/claim").status_code == 409
    assert client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).status_code == 201


def test_cancel_only_requested(client: TestClient) -> None:
    run = client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).json()
    client.post(f"/api/zac-sync-runs/{run['id']}/claim")
    assert client.post(f"/api/zac-sync-runs/{run['id']}/cancel").status_code == 409
    assert client.post("/api/zac-sync-runs/nope/cancel").status_code == 404


# ---- zac 状態 ----


def test_zac_status_derivation(client: TestClient, set_now: Callable[[str], None]) -> None:
    set_now("2026-10-13T09:00:00+09:00")
    run = start_run(client)
    finish_run(client, run["id"], "validation_failed")
    assert client.get(f"/api/work-reports/{DAY}").json()["zac_status"] == "needs_action"

    # 最新の実行が要対応でなければ null
    set_now("2026-10-13T10:00:00+09:00")
    run = start_run(client)
    finish_run(client, run["id"], "dry_run_done")
    assert client.get(f"/api/work-reports/{DAY}").json()["zac_status"] is None

    # 取り消した依頼は最新として扱わない
    set_now("2026-10-13T10:30:00+09:00")
    run = start_run(client)
    finish_run(client, run["id"], "needs_login")
    set_now("2026-10-13T11:00:00+09:00")
    request = client.post("/api/zac-sync-runs/requests", json={"work_date": DAY}).json()
    client.post(f"/api/zac-sync-runs/{request['id']}/cancel")
    assert client.get(f"/api/work-reports/{DAY}").json()["zac_status"] == "needs_action"

    set_now("2026-10-13T12:00:00+09:00")
    run = start_run(client)
    finish_run(client, run["id"], "succeeded")
    assert client.get(f"/api/work-reports/{DAY}").json()["zac_status"] == "registered"


@pytest.fixture()
def count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", before)
    yield statements
    event.remove(Engine, "before_cursor_execute", before)


def test_month_list_query_count_does_not_grow_with_days(
    client: TestClient, count_queries: list[str]
) -> None:
    def month_queries() -> int:
        count_queries.clear()
        reports = client.get("/api/work-reports", params={"year": 2026, "month": 10}).json()
        assert all("zac_status" in report for report in reports)
        return len(count_queries)

    run = start_run(client, day="2026-10-01")
    finish_run(client, run["id"], "failed")
    few = month_queries()
    for day in range(2, 20):
        run = start_run(client, day=f"2026-10-{day:02d}")
        finish_run(client, run["id"], "failed")
    many = month_queries()

    assert many == few
    reports = client.get("/api/work-reports", params={"year": 2026, "month": 10}).json()
    assert len(reports) == 19
    assert {report["zac_status"] for report in reports} == {"needs_action"}

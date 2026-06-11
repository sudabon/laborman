from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_status_transition_and_end_mail_body_policy(client: TestClient) -> None:
    work_date = "2026-06-06"

    start = client.post(
        f"/api/work-reports/{work_date}/record-start",
        json={"note": "朝会あり", "work_style": "remote"},
    )
    assert start.status_code == 200
    assert start.json()["status"] == "start_recorded"

    start_mail = client.post(
        f"/api/work-reports/{work_date}/mail-created",
        json={"kind": "start", "end_mail_body": "保存されない始業本文"},
    )
    assert start_mail.status_code == 200
    start_payload = start_mail.json()
    assert start_payload["status"] == "start_mail_created"
    assert start_payload["start_mail_created_at"] is not None
    assert start_payload["end_mail_body"] is None

    end = client.post(
        f"/api/work-reports/{work_date}/record-end",
        json={"note": "実装とレビュー", "work_style": "remote"},
    )
    assert end.status_code == 200
    assert end.json()["status"] == "end_recorded"

    end_mail = client.post(
        f"/api/work-reports/{work_date}/mail-created",
        json={"kind": "end", "end_mail_body": "日付: 2026/06/06\n勤務区分: リモート"},
    )
    assert end_mail.status_code == 200
    end_payload = end_mail.json()
    assert end_payload["status"] == "end_mail_created"
    assert end_payload["end_mail_created_at"] is not None
    assert end_payload["end_mail_body"] == "日付: 2026/06/06\n勤務区分: リモート"


def test_patch_saves_end_mail_body_draft(client: TestClient) -> None:
    work_date = "2026-06-08"
    draft = "本日の業務: 設計レビュー対応"

    saved = client.patch(
        f"/api/work-reports/{work_date}",
        json={"note": "メモ", "work_style": "remote", "end_mail_body": draft},
    )
    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["end_mail_body"] == draft
    assert saved_payload["status"] == "not_started"

    fetched = client.get(f"/api/work-reports/{work_date}")
    assert fetched.status_code == 200
    assert fetched.json()["end_mail_body"] == draft


def test_patch_clears_end_mail_body_draft_when_empty(client: TestClient) -> None:
    work_date = "2026-06-09"

    client.patch(
        f"/api/work-reports/{work_date}",
        json={"end_mail_body": "一時保存ドラフト"},
    )
    cleared = client.patch(
        f"/api/work-reports/{work_date}",
        json={"end_mail_body": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["end_mail_body"] is None


def test_settings_persist_boss_and_labor_ml_recipients(client: TestClient) -> None:
    read_default = client.get("/api/mail-settings")
    assert read_default.status_code == 200
    assert read_default.json()["boss_email"] == ""
    assert read_default.json()["labor_ml_email"] == ""

    saved = client.put(
        "/api/mail-settings",
        json={
            "boss_email": "boss@example.com",
            "labor_ml_email": "labor@example.com",
            "start_subject_template": "【始業報告】{{date}}",
            "start_body_template": "始業 {{work_style}}",
            "end_subject_template": "【終業報告】{{date}}",
            "end_header_template": "お疲れ様です。",
            "end_body_template": "勤務時間: {{work_duration}}",
            "end_footer_template": "よろしくお願いいたします。",
        },
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["boss_email"] == "boss@example.com"
    assert payload["labor_ml_email"] == "labor@example.com"


def test_end_record_without_start_keeps_duration_unknown(client: TestClient) -> None:
    work_date = "2026-06-07"

    response = client.post(
        f"/api/work-reports/{work_date}/record-end",
        json={"note": "", "work_style": "office"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "end_recorded"
    assert payload["start_time"] is None
    assert payload["work_duration_minutes"] is None

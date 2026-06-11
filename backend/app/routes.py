from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WorkReport
from app.repositories import (
    derive_status,
    get_mail_settings,
    get_report,
    list_reports_for_month,
    mark_mail_created,
    record_end,
    record_start,
    update_report,
    upsert_mail_settings,
    work_duration_minutes,
)
from app.schemas import (
    HealthRead,
    MailCreatedRequest,
    MailSettingsBase,
    MailSettingsRead,
    RecordEventRequest,
    WorkReportRead,
    WorkReportUpdate,
)

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_db)]


def serialize_report(report: WorkReport) -> WorkReportRead:
    return WorkReportRead.model_validate(
        {
            **report.__dict__,
            "status": derive_status(report),
            "work_duration_minutes": work_duration_minutes(report),
        }
    )


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok")


@router.get("/mail-settings", response_model=MailSettingsRead)
def read_mail_settings(db: SessionDep) -> MailSettingsRead:
    return MailSettingsRead.model_validate(get_mail_settings(db))


@router.put("/mail-settings", response_model=MailSettingsRead)
def save_mail_settings(payload: MailSettingsBase, db: SessionDep) -> MailSettingsRead:
    return MailSettingsRead.model_validate(upsert_mail_settings(db, payload))


@router.get("/work-reports", response_model=list[WorkReportRead])
def read_month_reports(
    db: SessionDep,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> list[WorkReportRead]:
    return [
        serialize_report(report) for report in list_reports_for_month(db, year, month)
    ]


@router.get("/work-reports/{work_date}", response_model=WorkReportRead)
def read_work_report(work_date: date, db: SessionDep) -> WorkReportRead:
    return serialize_report(get_report(db, work_date))


@router.patch("/work-reports/{work_date}", response_model=WorkReportRead)
def patch_work_report(
    work_date: date, payload: WorkReportUpdate, db: SessionDep
) -> WorkReportRead:
    return serialize_report(update_report(db, work_date, payload))


@router.post("/work-reports/{work_date}/record-start", response_model=WorkReportRead)
def post_record_start(
    work_date: date, payload: RecordEventRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_report(record_start(db, work_date, payload))


@router.post("/work-reports/{work_date}/record-end", response_model=WorkReportRead)
def post_record_end(
    work_date: date, payload: RecordEventRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_report(record_end(db, work_date, payload))


@router.post("/work-reports/{work_date}/mail-created", response_model=WorkReportRead)
def post_mail_created(
    work_date: date, payload: MailCreatedRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_report(mark_mail_created(db, work_date, payload))

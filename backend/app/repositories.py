from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MailSettings, WorkReport
from app.schemas import (
    DEFAULT_END_BODY_TEMPLATE,
    DEFAULT_END_FOOTER_TEMPLATE,
    DEFAULT_END_HEADER_TEMPLATE,
    DEFAULT_END_SUBJECT_TEMPLATE,
    DEFAULT_START_BODY_TEMPLATE,
    DEFAULT_START_SUBJECT_TEMPLATE,
    MailCreatedRequest,
    MailSettingsBase,
    RecordEventRequest,
    ReportStatus,
    WorkReportUpdate,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def default_mail_settings() -> MailSettings:
    return MailSettings(
        id="default",
        boss_email="",
        labor_ml_email="",
        cc_emails="",
        bcc_emails="",
        start_subject_template=DEFAULT_START_SUBJECT_TEMPLATE,
        start_body_template=DEFAULT_START_BODY_TEMPLATE,
        end_subject_template=DEFAULT_END_SUBJECT_TEMPLATE,
        end_header_template=DEFAULT_END_HEADER_TEMPLATE,
        end_body_template=DEFAULT_END_BODY_TEMPLATE,
        end_footer_template=DEFAULT_END_FOOTER_TEMPLATE,
    )


def get_mail_settings(db: Session) -> MailSettings:
    settings = db.get(MailSettings, "default")
    if settings is None:
        settings = default_mail_settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def upsert_mail_settings(db: Session, data: MailSettingsBase) -> MailSettings:
    settings = get_mail_settings(db)
    for field, value in data.model_dump().items():
        setattr(settings, field, value.strip() if isinstance(value, str) else value)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def get_or_create_report(db: Session, work_date: date) -> WorkReport:
    report = db.scalar(select(WorkReport).where(WorkReport.work_date == work_date))
    if report is None:
        report = WorkReport(work_date=work_date)
        db.add(report)
        db.commit()
        db.refresh(report)
    return report


def get_report(db: Session, work_date: date) -> WorkReport:
    return get_or_create_report(db, work_date)


def list_reports_for_month(db: Session, year: int, month: int) -> list[WorkReport]:
    start = date(year, month, 1)
    end = date(year + int(month == 12), 1 if month == 12 else month + 1, 1)
    return list(
        db.scalars(
            select(WorkReport)
            .where(WorkReport.work_date >= start)
            .where(WorkReport.work_date < end)
            .order_by(WorkReport.work_date)
        )
    )


def update_report(db: Session, work_date: date, data: WorkReportUpdate) -> WorkReport:
    report = get_or_create_report(db, work_date)
    payload = data.model_dump(exclude_unset=True)
    if "note" in payload and payload["note"] is not None:
        report.note = payload["note"]
    if "work_style" in payload and payload["work_style"] is not None:
        report.work_style = payload["work_style"]
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def record_start(db: Session, work_date: date, data: RecordEventRequest) -> WorkReport:
    report = update_report(db, work_date, data)
    report.start_time = now_utc()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def record_end(db: Session, work_date: date, data: RecordEventRequest) -> WorkReport:
    report = update_report(db, work_date, data)
    report.end_time = now_utc()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def mark_mail_created(db: Session, work_date: date, data: MailCreatedRequest) -> WorkReport:
    report = get_or_create_report(db, work_date)
    timestamp = now_utc()
    if data.kind == "start":
        report.start_mail_created_at = timestamp
    else:
        report.end_mail_created_at = timestamp
        report.end_mail_body = data.end_mail_body
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def derive_status(report: WorkReport) -> ReportStatus:
    if report.end_mail_created_at is not None:
        return "end_mail_created"
    if report.end_time is not None:
        return "end_recorded"
    if report.start_mail_created_at is not None:
        return "start_mail_created"
    if report.start_time is not None:
        return "start_recorded"
    return "not_started"


def work_duration_minutes(report: WorkReport) -> int | None:
    if report.start_time is None or report.end_time is None:
        return None
    seconds = (report.end_time - report.start_time).total_seconds()
    if seconds < 0:
        return None
    return int(seconds // 60)

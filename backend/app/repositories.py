from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AutomationSettings,
    Job,
    MailSettings,
    WorkBreak,
    WorkReport,
    WorkTask,
    ZacSalesItem,
    ZacSyncRun,
    ZacWorkKind,
)
from app.zac_months import normalize as normalize_zac_text
from app.zac_months import parse_valid_month, series_name_of
from app.schemas import (
    DEFAULT_END_BODY_TEMPLATE,
    DEFAULT_END_FOOTER_TEMPLATE,
    DEFAULT_END_HEADER_TEMPLATE,
    DEFAULT_END_SUBJECT_TEMPLATE,
    DEFAULT_START_BODY_TEMPLATE,
    DEFAULT_START_SUBJECT_TEMPLATE,
    AttendanceUpdate,
    AutomationSettingsBase,
    BreakCreate,
    BreakUpdate,
    JobCodeChange,
    JobCreate,
    JobUpdate,
    MailCreatedRequest,
    MailSettingsBase,
    RecordEventRequest,
    ReportStatus,
    TaskCreate,
    TaskStartRequest,
    TaskUpdate,
    WorkReportUpdate,
    WorkStyle,
    ZAC_NEEDS_ACTION_STATUSES,
    ZacDraftRead,
    ZacMasterImport,
    ZacMasterImportCounts,
    ZacMasterImportResult,
    ZacRunRequestCreate,
    ZacSalesItemCreate,
    ZacSalesItemUpdate,
    ZacTaskDefault,
    ZacWorkKindCreate,
    ZacWorkKindUpdate,
    ZacStatus,
    ZacSyncRunCreate,
    ZacSyncRunUpdate,
    ensure_utc,
)
from app.zac_draft import (
    AttendanceInput,
    BreakInput,
    DraftSettings,
    JobInfo,
    SalesItemInfo,
    TaskInput,
    build_zac_draft,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def default_mail_settings() -> MailSettings:
    return MailSettings(
        id="default",
        boss_email="",
        labor_ml_email="",
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


# 曜日（0=月曜）ごとの勤務区分の初期値。月・水はオフィス、それ以外はリモート
OFFICE_WEEKDAYS = {0, 2}


def default_work_style(work_date: date) -> WorkStyle:
    return "office" if work_date.weekday() in OFFICE_WEEKDAYS else "remote"


def get_or_create_report(db: Session, work_date: date) -> WorkReport:
    report = db.scalar(select(WorkReport).where(WorkReport.work_date == work_date))
    if report is None:
        report = WorkReport(work_date=work_date, work_style=default_work_style(work_date))
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
    if "end_mail_body" in payload:
        end_mail_body = payload["end_mail_body"]
        report.end_mail_body = end_mail_body if end_mail_body else None
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


def mark_mail_created(
    db: Session, work_date: date, data: MailCreatedRequest
) -> WorkReport:
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


class NotFoundError(Exception):
    pass


class InvalidInputError(Exception):
    pass


class ConflictError(Exception):
    def __init__(
        self, message: str, conflicts: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.conflicts = conflicts or []


# ---- ジョブマスタ ----


def list_jobs(db: Session, active: bool | None = None, q: str | None = None) -> list[Job]:
    query = select(Job)
    if active is not None:
        query = query.where(Job.is_active.is_(active))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Job.code.ilike(pattern), Job.name.ilike(pattern)))
    query = query.order_by(Job.last_used_at.desc().nulls_last(), Job.code)
    return list(db.scalars(query))


def create_job(db: Session, data: JobCreate) -> Job:
    if db.get(Job, data.code) is not None:
        raise ConflictError(f"ジョブ ID {data.code} はすでに登録されています")
    values = data.model_dump()
    if "series_name" not in data.model_fields_set:
        values["series_name"] = series_name_of(data.name)
    if "valid_month" not in data.model_fields_set:
        values["valid_month"] = parse_valid_month(data.name)
    job = Job(**values, is_active=True)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, code: str, data: JobUpdate) -> Job:
    job = db.get(Job, code)
    if job is None:
        raise NotFoundError(f"ジョブ ID {code} が見つかりません")
    for key, value in data.model_dump(exclude_unset=True).items():
        # シリーズ名・対象年月は null（空文字）で解除できる
        if value is not None or key in ("series_name", "valid_month"):
            setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job


def change_job_code(db: Session, code: str, data: JobCodeChange) -> Job:
    """新しい ID のジョブを作成し、元のジョブを無効化する（1 トランザクション）。

    記録済みのタスクは元の ID のまま残す（月替わりで ID が変わる業務の履歴を保つため）。
    """
    current = db.get(Job, code)
    if current is None:
        raise NotFoundError(f"ジョブ ID {code} が見つかりません")
    if data.code == code:
        raise InvalidInputError("変更後のジョブ ID が変更前と同じです")
    if db.get(Job, data.code) is not None:
        raise ConflictError(f"ジョブ ID {data.code} はすでに登録されています")
    created = Job(
        code=data.code,
        name=data.name if data.name is not None else current.name,
        zac_search_text=(
            data.zac_search_text if data.zac_search_text is not None else current.zac_search_text
        ),
        zac_work_category=(
            data.zac_work_category
            if data.zac_work_category is not None
            else current.zac_work_category
        ),
        is_active=True,
        # 最近使った順の位置を引き継ぐ
        last_used_at=current.last_used_at,
    )
    db.add(created)
    current.is_active = False
    db.commit()
    db.refresh(created)
    return created


# ---- タスク・休憩 ----

EntryKind = Literal["task", "break"]
# 勤務日の範囲は 00:00〜翌 06:00（24:00〜29:59 を翌日として受け付ける）
WORK_DAY_END_HOUR_NEXT_DAY = 6


def work_day_range(work_date: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(get_settings().app_timezone)
    start = datetime.combine(work_date, time(0, 0), tzinfo=tz)
    end = datetime.combine(
        work_date + timedelta(days=1), time(WORK_DAY_END_HOUR_NEXT_DAY, 0), tzinfo=tz
    )
    return start.astimezone(UTC), end.astimezone(UTC)


def utc(value: datetime) -> datetime:
    converted = ensure_utc(value)
    assert converted is not None
    return converted


def find_report(db: Session, work_date: date) -> WorkReport | None:
    return db.scalar(select(WorkReport).where(WorkReport.work_date == work_date))


def validate_entry_times(
    work_date: date, start_at: datetime, end_at: datetime | None
) -> None:
    day_start, day_end = work_day_range(work_date)
    for value in (start_at, end_at):
        if value is None:
            continue
        if not (day_start <= value < day_end):
            raise InvalidInputError(
                "時刻は勤務日の 00:00 から翌日 06:00（29:59）までの範囲で入力してください"
            )
    if end_at is not None and end_at <= start_at:
        raise InvalidInputError("終了時刻は開始時刻より後にしてください")


def ensure_job_exists(db: Session, job_code: str) -> Job:
    job = db.get(Job, job_code)
    if job is None:
        raise InvalidInputError(f"ジョブ ID {job_code} は登録されていません")
    return job


def describe_entry(kind: EntryKind, entry: WorkTask | WorkBreak) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": entry.id,
        "start_at": utc(entry.start_at).isoformat(),
        "end_at": utc(entry.end_at).isoformat() if entry.end_at else None,
    }


def ensure_single_running(
    report: WorkReport, kind: EntryKind, exclude_id: str | None = None
) -> None:
    entries: list[WorkTask] | list[WorkBreak] = (
        report.tasks if kind == "task" else report.breaks
    )
    running = [e for e in entries if e.end_at is None and e.id != exclude_id]
    if running:
        label = "タスク" if kind == "task" else "休憩"
        raise ConflictError(
            f"進行中の{label}がすでにあります",
            [describe_entry(kind, entry) for entry in running],
        )


def commit_entry(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("進行中のタスク・休憩は 1 件までです") from exc


def touch_job(job: Job, now: datetime) -> None:
    job.last_used_at = now


def sorted_tasks(report: WorkReport | None) -> list[WorkTask]:
    if report is None:
        return []
    return sorted(report.tasks, key=lambda task: utc(task.start_at))


def sorted_breaks(report: WorkReport | None) -> list[WorkBreak]:
    if report is None:
        return []
    return sorted(report.breaks, key=lambda item: utc(item.start_at))


def list_tasks(db: Session, work_date: date) -> list[WorkTask]:
    return sorted_tasks(find_report(db, work_date))


def list_breaks(db: Session, work_date: date) -> list[WorkBreak]:
    return sorted_breaks(find_report(db, work_date))


def get_task(db: Session, task_id: str) -> WorkTask:
    task = db.get(WorkTask, task_id)
    if task is None:
        raise NotFoundError("タスクが見つかりません")
    return task


def get_break(db: Session, break_id: str) -> WorkBreak:
    item = db.get(WorkBreak, break_id)
    if item is None:
        raise NotFoundError("休憩が見つかりません")
    return item


def stop_running_entries(
    db: Session, report: WorkReport, now: datetime
) -> None:
    """進行中のタスク・休憩を now で終了する（コミットはしない）。"""
    for task in report.tasks:
        if task.end_at is None:
            close_entry(db, report, "task", task, now)
    for item in report.breaks:
        if item.end_at is None:
            close_entry(db, report, "break", item, now)


def close_entry(
    db: Session,
    report: WorkReport,
    kind: EntryKind,
    entry: WorkTask | WorkBreak,
    now: datetime,
) -> None:
    start_at = utc(entry.start_at)
    validate_entry_times(report.work_date, start_at, now)
    entry.end_at = now
    db.flush()


def ensure_work_kind(db: Session, name: str | None) -> None:
    if name is not None and db.get(ZacWorkKind, name) is None:
        raise InvalidInputError(f"作業内容「{name}」は登録されていません")


def ensure_sales_item_of_job(db: Session, sales_item_id: str | None, job_code: str) -> None:
    if sales_item_id is None:
        return
    item = db.get(ZacSalesItem, sales_item_id)
    if item is None:
        raise InvalidInputError("売上項目が見つかりません")
    if item.job_code != job_code:
        raise InvalidInputError(f"売上項目「{item.name}」はジョブ {job_code} の売上項目ではありません")


def create_task(db: Session, work_date: date, data: TaskCreate) -> WorkTask:
    now = now_utc()
    start_at = utc(data.start_at)
    end_at = ensure_utc(data.end_at)
    validate_entry_times(work_date, start_at, end_at)
    job = ensure_job_exists(db, data.job_code)
    ensure_work_kind(db, data.work_kind)
    ensure_sales_item_of_job(db, data.sales_item_id, job.code)
    report = get_or_create_report(db, work_date)
    if end_at is None:
        ensure_single_running(report, "task")
    task = WorkTask(
        work_report_id=report.id,
        job_code=job.code,
        description=data.description,
        work_kind=data.work_kind,
        sales_item_id=data.sales_item_id,
        start_at=start_at,
        end_at=end_at,
    )
    db.add(task)
    touch_job(job, now)
    commit_entry(db)
    db.refresh(task)
    return task


def update_task(db: Session, task_id: str, data: TaskUpdate) -> WorkTask:
    task = get_task(db, task_id)
    report = task.work_report
    payload = data.model_dump(exclude_unset=True)
    if payload.get("start_at") is None and "start_at" in payload:
        raise InvalidInputError("開始時刻は必須です")
    start_at = utc(payload.get("start_at", task.start_at))
    end_at = ensure_utc(payload["end_at"]) if "end_at" in payload else ensure_utc(task.end_at)
    validate_entry_times(report.work_date, start_at, end_at)
    job_code = payload.get("job_code") or task.job_code
    ensure_job_exists(db, job_code)
    work_kind = payload["work_kind"] if "work_kind" in payload else task.work_kind
    if "sales_item_id" in payload:
        sales_item_id = payload["sales_item_id"]
    else:
        # ジョブを変えたときは、元のジョブの売上項目を引き継がない
        sales_item_id = task.sales_item_id if job_code == task.job_code else None
    ensure_work_kind(db, work_kind)
    ensure_sales_item_of_job(db, sales_item_id, job_code)
    if end_at is None:
        ensure_single_running(report, "task", exclude_id=task.id)
    task.job_code = job_code
    task.work_kind = work_kind
    task.sales_item_id = sales_item_id
    if payload.get("description") is not None:
        task.description = payload["description"]
    task.start_at = start_at
    task.end_at = end_at
    commit_entry(db)
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: str) -> None:
    task = get_task(db, task_id)
    db.delete(task)
    db.commit()


def start_task(db: Session, work_date: date, data: TaskStartRequest) -> WorkTask:
    now = now_utc()
    validate_entry_times(work_date, now, None)
    job = ensure_job_exists(db, data.job_code)
    report = get_or_create_report(db, work_date)
    try:
        stop_running_entries(db, report, now)
        task = WorkTask(
            work_report_id=report.id,
            job_code=job.code,
            description=data.description,
            start_at=now,
            end_at=None,
        )
        db.add(task)
        touch_job(job, now)
        commit_entry(db)
    except Exception:
        db.rollback()
        raise
    db.refresh(task)
    return task


def stop_task(db: Session, task_id: str) -> WorkTask:
    task = get_task(db, task_id)
    if task.end_at is not None:
        raise ConflictError("このタスクはすでに終了しています")
    try:
        close_entry(db, task.work_report, "task", task, now_utc())
        commit_entry(db)
    except Exception:
        db.rollback()
        raise
    db.refresh(task)
    return task


def create_break(
    db: Session, work_date: date, data: BreakCreate, source: str = "manual"
) -> WorkBreak:
    start_at = utc(data.start_at)
    end_at = ensure_utc(data.end_at)
    validate_entry_times(work_date, start_at, end_at)
    report = get_or_create_report(db, work_date)
    if end_at is None:
        ensure_single_running(report, "break")
    item = WorkBreak(
        work_report_id=report.id, start_at=start_at, end_at=end_at, source=source
    )
    db.add(item)
    commit_entry(db)
    db.refresh(item)
    return item


def update_break(db: Session, break_id: str, data: BreakUpdate) -> WorkBreak:
    item = get_break(db, break_id)
    report = item.work_report
    payload = data.model_dump(exclude_unset=True)
    if payload.get("start_at") is None and "start_at" in payload:
        raise InvalidInputError("開始時刻は必須です")
    start_at = utc(payload.get("start_at", item.start_at))
    end_at = ensure_utc(payload["end_at"]) if "end_at" in payload else ensure_utc(item.end_at)
    validate_entry_times(report.work_date, start_at, end_at)
    if end_at is None:
        ensure_single_running(report, "break", exclude_id=item.id)
    item.start_at = start_at
    item.end_at = end_at
    commit_entry(db)
    db.refresh(item)
    return item


def delete_break(db: Session, break_id: str) -> None:
    item = get_break(db, break_id)
    db.delete(item)
    db.commit()


def start_break(db: Session, work_date: date) -> WorkBreak:
    now = now_utc()
    validate_entry_times(work_date, now, None)
    report = get_or_create_report(db, work_date)
    try:
        stop_running_entries(db, report, now)
        item = WorkBreak(
            work_report_id=report.id, start_at=now, end_at=None, source="manual"
        )
        db.add(item)
        commit_entry(db)
    except Exception:
        db.rollback()
        raise
    db.refresh(item)
    return item


def stop_break(db: Session, break_id: str) -> WorkBreak:
    item = get_break(db, break_id)
    if item.end_at is not None:
        raise ConflictError("この休憩はすでに終了しています")
    try:
        close_entry(db, item.work_report, "break", item, now_utc())
        commit_entry(db)
    except Exception:
        db.rollback()
        raise
    db.refresh(item)
    return item


# ---- 出退勤実績 ----

# 出退勤に合わせて最初・最後のタスクの時刻を直す、ずれの上限
ATTENDANCE_ALIGN_MAX = timedelta(minutes=30)


def update_attendance(
    db: Session, work_date: date, data: AttendanceUpdate
) -> WorkReport:
    """出退勤実績を登録する。手入力（manual）の日に人事メール（hr_mail）は上書きしない。"""
    start_at = ensure_utc(data.start_at)
    end_at = ensure_utc(data.end_at)
    if data.source == "hr_mail" and data.kind == "leave":
        raise InvalidInputError("人事メールから休暇は登録できません")
    if data.kind == "work":
        if start_at is None or end_at is None:
            raise InvalidInputError("勤務の出退勤実績には出勤・退勤の両方が必要です")
        validate_entry_times(work_date, start_at, end_at)
    elif start_at is not None:
        validate_entry_times(work_date, start_at, end_at)
    elif end_at is not None:
        validate_entry_times(work_date, end_at, None)

    report = get_or_create_report(db, work_date)
    if data.source == "hr_mail" and report.attendance_source == "manual":
        raise ConflictError("手入力済みの出退勤実績は人事メールで上書きできません")
    report.attendance_start_at = start_at
    report.attendance_end_at = end_at
    report.attendance_source = data.source
    report.attendance_kind = data.kind
    if data.source == "hr_mail":
        report.attendance_imported_at = now_utc()
    if data.kind == "work" and start_at is not None and end_at is not None:
        align_tasks_to_attendance(report, start_at, end_at)
    db.commit()
    db.refresh(report)
    return report


def align_tasks_to_attendance(report: WorkReport, start_at: datetime, end_at: datetime) -> None:
    """最初のタスクの開始と最後のタスクの終了を、出退勤の時刻に合わせる（コミットはしない）。

    ずれが ATTENDANCE_ALIGN_MAX を超えるときは記録漏れの可能性があるため直さない。
    zac 登録済みの日、端に休憩がある日、進行中のタスクの終了、タスクが空になる変更は直さない。
    """
    if report.zac_registered_at is not None:
        return
    tasks = sorted_tasks(report)
    if not tasks:
        return
    breaks = sorted_breaks(report)
    first = tasks[0]
    first_start = utc(first.start_at)
    if (
        abs(first_start - start_at) <= ATTENDANCE_ALIGN_MAX
        and not any(utc(item.start_at) < first_start for item in breaks)
        and (first.end_at is None or start_at < utc(first.end_at))
    ):
        first.start_at = start_at
    ends = [(utc(task.end_at), task) for task in tasks if task.end_at is not None]
    if len(ends) < len(tasks):
        return
    last_end, last = max(ends, key=lambda pair: pair[0])
    if (
        abs(last_end - end_at) <= ATTENDANCE_ALIGN_MAX
        and not any(item.end_at is not None and utc(item.end_at) > last_end for item in breaks)
        and utc(last.start_at) < end_at
    ):
        last.end_at = end_at


# ---- 自動化設定 ----


def get_automation_settings(db: Session) -> AutomationSettings:
    settings = db.get(AutomationSettings, "default")
    if settings is None:
        settings = AutomationSettings(
            id="default", default_break_start="12:00", default_break_end="13:00"
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def upsert_automation_settings(
    db: Session, data: AutomationSettingsBase
) -> AutomationSettings:
    if data.default_job_code is not None:
        ensure_job_exists(db, data.default_job_code)
    ensure_work_kind(db, data.default_work_kind)
    if data.default_sales_item_id is not None:
        ensure_sales_item_of_job(db, data.default_sales_item_id, data.default_job_code or "")
    settings = get_automation_settings(db)
    for key, value in data.model_dump().items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


# ---- zac 登録ドラフト ----


def read_automation_settings(db: Session) -> AutomationSettings:
    """自動化設定を読む。行がなければ既定値（DB には保存しない）。"""
    return db.get(AutomationSettings, "default") or AutomationSettings(
        id="default",
        default_break_start="12:00",
        default_break_end="13:00",
        hr_mail_from="",
        hr_mail_subject_keyword="",
        zac_submit_mode="dry_run",
        entry_style="duration",
        time_unit_minutes=15,
        clip_tolerance_minutes=15,
        gap_policy="block",
        default_job_code=None,
        default_work_kind=None,
        default_sales_item_id=None,
        description_max_length=100,
    )


def build_report_zac_draft(db: Session, work_date: date) -> ZacDraftRead:
    """勤務日のドラフトを算出する。報告がなくても作成しない（DB を変更しない）。"""
    report = find_report(db, work_date)
    settings = read_automation_settings(db)
    jobs = {
        job.code: JobInfo(job.code, job.zac_search_text, job.name, job.valid_month)
        for job in db.scalars(select(Job))
    }
    sales_items = {
        item.id: SalesItemInfo(item.id, item.job_code, item.name, item.valid_month)
        for item in db.scalars(select(ZacSalesItem))
    }
    attendance = AttendanceInput(
        start_at=ensure_utc(report.attendance_start_at) if report else None,
        end_at=ensure_utc(report.attendance_end_at) if report else None,
        source=report.attendance_source if report else None,
        kind=report.attendance_kind if report else "work",
    )
    return build_zac_draft(
        work_date=work_date,
        attendance=attendance,
        tasks=[
            TaskInput(
                t.id,
                t.job_code,
                t.description,
                utc(t.start_at),
                ensure_utc(t.end_at),
                work_kind=t.work_kind,
                sales_item_id=t.sales_item_id,
            )
            for t in sorted_tasks(report)
        ],
        breaks=[
            BreakInput(b.id, utc(b.start_at), ensure_utc(b.end_at)) for b in sorted_breaks(report)
        ],
        jobs=jobs,
        settings=DraftSettings(
            entry_style="time_range" if settings.entry_style == "time_range" else "duration",
            time_unit_minutes=settings.time_unit_minutes,
            clip_tolerance_minutes=settings.clip_tolerance_minutes,
            gap_policy=settings.gap_policy,
            default_job_code=settings.default_job_code,
            default_work_kind=settings.default_work_kind,
            default_sales_item_id=settings.default_sales_item_id,
            description_max_length=settings.description_max_length,
        ),
        sales_items=sales_items,
        tz=ZoneInfo(get_settings().app_timezone),
        zac_registered_at=ensure_utc(report.zac_registered_at) if report else None,
    )


# ---- zac 連携の実行履歴 ----

# 実行中のまま残った記録（エージェントの異常終了など）が新しい依頼を塞がないよう、この時間で無視する
STALE_RUNNING = timedelta(minutes=60)
# 依頼中・実行中を除いた結果の状態（終了日時を設定する）
OPEN_RUN_STATUSES = ("requested", "running")


def get_zac_run(db: Session, run_id: str) -> ZacSyncRun:
    run = db.get(ZacSyncRun, run_id)
    if run is None:
        raise NotFoundError("実行履歴が見つかりません")
    return run


def list_zac_runs(
    db: Session,
    work_date: date | None = None,
    status: str | None = None,
    oldest_first: bool = False,
    limit: int = 50,
) -> list[ZacSyncRun]:
    query = select(ZacSyncRun)
    if work_date is not None:
        query = query.where(ZacSyncRun.work_date == work_date)
    if status is not None:
        query = query.where(ZacSyncRun.status == status)
    order = ZacSyncRun.started_at.asc() if oldest_first else ZacSyncRun.started_at.desc()
    return list(db.scalars(query.order_by(order).limit(limit)))


def create_zac_run(db: Session, data: ZacSyncRunCreate) -> ZacSyncRun:
    # カレンダーに状態を出せるよう、報告がなければ作る
    get_or_create_report(db, data.work_date)
    run = ZacSyncRun(
        work_date=data.work_date,
        mode=data.mode,
        status="running",
        agent_version=data.agent_version,
        started_at=now_utc(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_zac_run(db: Session, run_id: str, data: ZacSyncRunUpdate) -> ZacSyncRun:
    run = get_zac_run(db, run_id)
    now = now_utc()
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "status" and value is None:
            continue
        setattr(run, key, value)
    if run.status not in OPEN_RUN_STATUSES and run.finished_at is None:
        run.finished_at = now
    if data.status == "succeeded":
        report = get_or_create_report(db, run.work_date)
        report.zac_registered_at = now
    db.commit()
    db.refresh(run)
    return run


def request_zac_run(db: Session, data: ZacRunRequestCreate) -> ZacSyncRun:
    """画面からの実行依頼。同じ日に依頼中・実行中があれば 409。"""
    now = now_utc()
    open_run = db.scalar(
        select(ZacSyncRun).where(
            ZacSyncRun.work_date == data.work_date,
            or_(
                ZacSyncRun.status == "requested",
                and_(ZacSyncRun.status == "running", ZacSyncRun.started_at > now - STALE_RUNNING),
            ),
        )
    )
    if open_run is not None:
        raise ConflictError("この日の zac 登録はすでに依頼中または実行中です")
    get_or_create_report(db, data.work_date)
    run = ZacSyncRun(
        work_date=data.work_date,
        mode=read_automation_settings(db).zac_submit_mode,
        status="requested",
        started_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def transition_zac_run(
    db: Session, run_id: str, *, to_status: str, finished: bool, conflict_message: str
) -> ZacSyncRun:
    """requested の依頼だけを条件付きで更新する（二重取得・取り消しの競合を防ぐ）。"""
    now = now_utc()
    values: dict[str, Any] = {"status": to_status}
    if finished:
        values["finished_at"] = now
    else:
        values["started_at"] = now
    result = db.execute(
        update(ZacSyncRun)
        .where(ZacSyncRun.id == run_id, ZacSyncRun.status == "requested")
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount == 0:  # type: ignore[attr-defined]
        get_zac_run(db, run_id)
        raise ConflictError(conflict_message)
    run = get_zac_run(db, run_id)
    db.refresh(run)
    return run


def claim_zac_run(db: Session, run_id: str) -> ZacSyncRun:
    return transition_zac_run(
        db,
        run_id,
        to_status="running",
        finished=False,
        conflict_message="この依頼はすでに処理中か、取り消されています",
    )


def cancel_zac_run(db: Session, run_id: str) -> ZacSyncRun:
    return transition_zac_run(
        db,
        run_id,
        to_status="cancelled",
        finished=True,
        conflict_message="依頼中ではないため取り消せません",
    )


def latest_zac_run_statuses(
    db: Session, start: date, end: date
) -> dict[date, str]:
    """[start, end) の勤務日ごとの最新の実行結果の状態（取り消した依頼は除く）を 1 クエリで返す。"""
    latest = (
        select(ZacSyncRun.work_date, func.max(ZacSyncRun.started_at).label("latest"))
        .where(
            ZacSyncRun.work_date >= start,
            ZacSyncRun.work_date < end,
            ZacSyncRun.status != "cancelled",
        )
        .group_by(ZacSyncRun.work_date)
        .subquery()
    )
    rows = db.execute(
        select(ZacSyncRun.work_date, ZacSyncRun.status).join(
            latest,
            and_(
                ZacSyncRun.work_date == latest.c.work_date,
                ZacSyncRun.started_at == latest.c.latest,
            ),
        )
    )
    return {row.work_date: row.status for row in rows}


def derive_zac_status(report: WorkReport, latest_status: str | None) -> ZacStatus | None:
    if report.zac_registered_at is not None:
        return "registered"
    if latest_status in ZAC_NEEDS_ACTION_STATUSES:
        return "needs_action"
    return None


# ---- zac の作業内容・売上項目 ----


def list_work_kinds(db: Session, active: bool | None = None) -> list[ZacWorkKind]:
    query = select(ZacWorkKind)
    if active is not None:
        query = query.where(ZacWorkKind.is_active.is_(active))
    return list(db.scalars(query.order_by(ZacWorkKind.sort_order, ZacWorkKind.name)))


def create_work_kind(db: Session, data: ZacWorkKindCreate) -> ZacWorkKind:
    if db.get(ZacWorkKind, data.name) is not None:
        raise ConflictError(f"作業内容「{data.name}」はすでに登録されています")
    order = (db.scalar(select(func.max(ZacWorkKind.sort_order))) or 0) + 1
    kind = ZacWorkKind(name=data.name, is_active=True, sort_order=order)
    db.add(kind)
    db.commit()
    db.refresh(kind)
    return kind


def update_work_kind(db: Session, name: str, data: ZacWorkKindUpdate) -> ZacWorkKind:
    kind = db.get(ZacWorkKind, name)
    if kind is None:
        raise NotFoundError(f"作業内容「{name}」が見つかりません")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(kind, key, value)
    db.commit()
    db.refresh(kind)
    return kind


def list_sales_items(
    db: Session, job_code: str | None = None, active: bool | None = None
) -> list[ZacSalesItem]:
    query = select(ZacSalesItem)
    if job_code is not None:
        query = query.where(ZacSalesItem.job_code == job_code)
    if active is not None:
        query = query.where(ZacSalesItem.is_active.is_(active))
    return list(
        db.scalars(query.order_by(ZacSalesItem.job_code, ZacSalesItem.sort_order, ZacSalesItem.name))
    )


def create_sales_item(db: Session, job_code: str, data: ZacSalesItemCreate) -> ZacSalesItem:
    job = db.get(Job, job_code)
    if job is None:
        raise NotFoundError(f"ジョブ ID {job_code} が見つかりません")
    exists = db.scalar(
        select(ZacSalesItem).where(ZacSalesItem.job_code == job_code, ZacSalesItem.name == data.name)
    )
    if exists is not None:
        raise ConflictError(f"売上項目「{data.name}」はすでに登録されています")
    order = (
        db.scalar(select(func.max(ZacSalesItem.sort_order)).where(ZacSalesItem.job_code == job_code))
        or 0
    ) + 1
    item = ZacSalesItem(
        job_code=job_code,
        name=data.name,
        valid_month=parse_valid_month(data.name),
        is_closed=data.is_closed,
        is_active=True,
        sort_order=order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_sales_item(db: Session, item_id: str, data: ZacSalesItemUpdate) -> ZacSalesItem:
    item = db.get(ZacSalesItem, item_id)
    if item is None:
        raise NotFoundError("売上項目が見つかりません")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def import_zac_masters(db: Session, data: ZacMasterImport) -> ZacMasterImportResult:
    """zac の選択肢を追加・更新する。今回現れなかったものは無効化しない（1 トランザクション）。"""
    created = ZacMasterImportCounts()
    updated = ZacMasterImportCounts()

    for order, raw_name in enumerate(data.work_kinds, start=1):
        name = raw_name.strip()
        if not name:
            continue
        kind = db.get(ZacWorkKind, name)
        if kind is None:
            db.add(ZacWorkKind(name=name, is_active=True, sort_order=order))
            created.work_kinds += 1
        elif kind.sort_order != order:
            kind.sort_order = order
            updated.work_kinds += 1

    seen: set[str] = set()
    skipped: list[str] = []
    for project in data.projects:
        code = project.code.strip()
        name = project.name.strip()
        month = parse_valid_month(name)
        if data.as_of_month and month and month < data.as_of_month:
            skipped.append(code)
            continue
        seen.add(code)
        job = db.get(Job, code)
        derived = {"series_name": series_name_of(name), "valid_month": parse_valid_month(name)}
        if job is None:
            job = Job(code=code, name=name, zac_search_text="", zac_work_category="", is_active=True, **derived)
            db.add(job)
            created.jobs += 1
        elif (job.name, job.series_name, job.valid_month) != (name, derived["series_name"], derived["valid_month"]):
            job.name = name
            job.series_name = derived["series_name"]
            job.valid_month = derived["valid_month"]
            updated.jobs += 1
        db.flush()

        existing = {
            normalize_zac_text(item.name): item
            for item in db.scalars(select(ZacSalesItem).where(ZacSalesItem.job_code == code))
        }
        for order, sales in enumerate(project.sales_items, start=1):
            item = existing.get(normalize_zac_text(sales.name))
            if item is None:
                db.add(
                    ZacSalesItem(
                        job_code=code,
                        name=sales.name.strip(),
                        valid_month=parse_valid_month(sales.name),
                        is_closed=sales.is_closed,
                        is_active=True,
                        sort_order=order,
                    )
                )
                created.sales_items += 1
            elif (item.is_closed, item.sort_order) != (sales.is_closed, order):
                item.is_closed = sales.is_closed
                item.sort_order = order
                updated.sales_items += 1

    missing = [
        job.code
        for job in db.scalars(select(Job).where(Job.is_active.is_(True)).order_by(Job.code))
        if job.code not in seen
    ]
    db.commit()
    return ZacMasterImportResult(
        created=created, updated=updated, missing_jobs=missing, skipped_jobs=skipped
    )


def zac_task_defaults(db: Session) -> list[ZacTaskDefault]:
    """ジョブごとに、作業内容・売上項目それぞれの直近の値（開始時刻が最も新しいタスク）を返す。"""
    latest: dict[str, ZacTaskDefault] = {}
    rows = db.execute(
        select(WorkTask.job_code, WorkTask.work_kind, WorkTask.sales_item_id)
        .where(or_(WorkTask.work_kind.is_not(None), WorkTask.sales_item_id.is_not(None)))
        .order_by(WorkTask.start_at.desc())
    )
    for job_code, work_kind, sales_item_id in rows:
        current = latest.setdefault(job_code, ZacTaskDefault(job_code=job_code))
        if current.work_kind is None and work_kind is not None:
            current.work_kind = work_kind
        if current.sales_item_id is None and sales_item_id is not None:
            current.sales_item_id = sales_item_id
    return sorted(latest.values(), key=lambda item: item.job_code)


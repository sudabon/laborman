from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app import repositories as repo
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
    AttendanceUpdate,
    AutomationSettingsBase,
    AutomationSettingsRead,
    BreakCreate,
    BreakRead,
    BreakUpdate,
    HealthRead,
    JobCodeChange,
    JobCreate,
    JobRead,
    JobUpdate,
    MailCreatedRequest,
    MailSettingsBase,
    MailSettingsRead,
    RecordEventRequest,
    TaskCreate,
    TaskRead,
    TaskStartRequest,
    TaskUpdate,
    WorkReportRead,
    WorkReportUpdate,
    ZacDraftRead,
    ZacMasterImport,
    ZacMasterImportResult,
    ZacRunRequestCreate,
    ZacSalesItemCreate,
    ZacSalesItemRead,
    ZacSalesItemUpdate,
    ZacTaskDefault,
    ZacWorkKindCreate,
    ZacWorkKindRead,
    ZacWorkKindUpdate,
    ZacSyncRunCreate,
    ZacSyncRunRead,
    ZacSyncRunUpdate,
)

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_db)]


def serialize_report(
    report: WorkReport, latest_zac_status: str | None = None
) -> WorkReportRead:
    return WorkReportRead.model_validate(
        {
            **report.__dict__,
            "status": derive_status(report),
            "work_duration_minutes": work_duration_minutes(report),
            "zac_status": repo.derive_zac_status(report, latest_zac_status),
        }
    )


def serialize_one(db: Session, report: WorkReport) -> WorkReportRead:
    next_day = report.work_date + timedelta(days=1)
    statuses = repo.latest_zac_run_statuses(db, report.work_date, next_day)
    return serialize_report(report, statuses.get(report.work_date))


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
    start = date(year, month, 1)
    end = date(year + int(month == 12), 1 if month == 12 else month + 1, 1)
    statuses = repo.latest_zac_run_statuses(db, start, end)
    return [
        serialize_report(report, statuses.get(report.work_date))
        for report in list_reports_for_month(db, year, month)
    ]


@router.get("/work-reports/{work_date}", response_model=WorkReportRead)
def read_work_report(work_date: date, db: SessionDep) -> WorkReportRead:
    return serialize_one(db, get_report(db, work_date))


@router.patch("/work-reports/{work_date}", response_model=WorkReportRead)
def patch_work_report(
    work_date: date, payload: WorkReportUpdate, db: SessionDep
) -> WorkReportRead:
    return serialize_one(db, update_report(db, work_date, payload))


@router.post("/work-reports/{work_date}/record-start", response_model=WorkReportRead)
def post_record_start(
    work_date: date, payload: RecordEventRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_one(db, record_start(db, work_date, payload))


@router.post("/work-reports/{work_date}/record-end", response_model=WorkReportRead)
def post_record_end(
    work_date: date, payload: RecordEventRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_one(db, record_end(db, work_date, payload))


@router.post("/work-reports/{work_date}/mail-created", response_model=WorkReportRead)
def post_mail_created(
    work_date: date, payload: MailCreatedRequest, db: SessionDep
) -> WorkReportRead:
    return serialize_one(db, mark_mail_created(db, work_date, payload))


@router.put("/work-reports/{work_date}/attendance", response_model=WorkReportRead)
def put_attendance(
    work_date: date, payload: AttendanceUpdate, db: SessionDep
) -> WorkReportRead:
    return serialize_one(db, repo.update_attendance(db, work_date, payload))


@router.get("/work-reports/{work_date}/zac-draft", response_model=ZacDraftRead)
def read_zac_draft(work_date: date, db: SessionDep) -> ZacDraftRead:
    return repo.build_report_zac_draft(db, work_date)


@router.get("/jobs", response_model=list[JobRead])
def read_jobs(
    db: SessionDep, active: bool | None = None, q: str | None = None
) -> list[JobRead]:
    return [JobRead.model_validate(job) for job in repo.list_jobs(db, active, q)]


@router.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def post_job(payload: JobCreate, db: SessionDep) -> JobRead:
    return JobRead.model_validate(repo.create_job(db, payload))


@router.patch("/jobs/{code}", response_model=JobRead)
def patch_job(code: str, payload: JobUpdate, db: SessionDep) -> JobRead:
    return JobRead.model_validate(repo.update_job(db, code, payload))


@router.post(
    "/jobs/{code}/change-code",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
def post_job_change_code(code: str, payload: JobCodeChange, db: SessionDep) -> JobRead:
    return JobRead.model_validate(repo.change_job_code(db, code, payload))


@router.get("/work-reports/{work_date}/tasks", response_model=list[TaskRead])
def read_tasks(work_date: date, db: SessionDep) -> list[TaskRead]:
    return [TaskRead.model_validate(task) for task in repo.list_tasks(db, work_date)]


@router.post(
    "/work-reports/{work_date}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def post_task(work_date: date, payload: TaskCreate, db: SessionDep) -> TaskRead:
    return TaskRead.model_validate(repo.create_task(db, work_date, payload))


@router.post(
    "/work-reports/{work_date}/tasks/start",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def post_task_start(
    work_date: date, payload: TaskStartRequest, db: SessionDep
) -> TaskRead:
    return TaskRead.model_validate(repo.start_task(db, work_date, payload))


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def patch_task(task_id: str, payload: TaskUpdate, db: SessionDep) -> TaskRead:
    return TaskRead.model_validate(repo.update_task(db, task_id, payload))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task(task_id: str, db: SessionDep) -> Response:
    repo.delete_task(db, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tasks/{task_id}/stop", response_model=TaskRead)
def post_task_stop(task_id: str, db: SessionDep) -> TaskRead:
    return TaskRead.model_validate(repo.stop_task(db, task_id))


@router.get("/work-reports/{work_date}/breaks", response_model=list[BreakRead])
def read_breaks(work_date: date, db: SessionDep) -> list[BreakRead]:
    return [BreakRead.model_validate(item) for item in repo.list_breaks(db, work_date)]


@router.post(
    "/work-reports/{work_date}/breaks",
    response_model=BreakRead,
    status_code=status.HTTP_201_CREATED,
)
def post_break(work_date: date, payload: BreakCreate, db: SessionDep) -> BreakRead:
    return BreakRead.model_validate(repo.create_break(db, work_date, payload))


@router.post(
    "/work-reports/{work_date}/breaks/start",
    response_model=BreakRead,
    status_code=status.HTTP_201_CREATED,
)
def post_break_start(work_date: date, db: SessionDep) -> BreakRead:
    return BreakRead.model_validate(repo.start_break(db, work_date))


@router.patch("/breaks/{break_id}", response_model=BreakRead)
def patch_break(break_id: str, payload: BreakUpdate, db: SessionDep) -> BreakRead:
    return BreakRead.model_validate(repo.update_break(db, break_id, payload))


@router.delete("/breaks/{break_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_break(break_id: str, db: SessionDep) -> Response:
    repo.delete_break(db, break_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/breaks/{break_id}/stop", response_model=BreakRead)
def post_break_stop(break_id: str, db: SessionDep) -> BreakRead:
    return BreakRead.model_validate(repo.stop_break(db, break_id))


@router.get("/automation-settings", response_model=AutomationSettingsRead)
def read_automation_settings(db: SessionDep) -> AutomationSettingsRead:
    return AutomationSettingsRead.model_validate(repo.get_automation_settings(db))


@router.put("/automation-settings", response_model=AutomationSettingsRead)
def save_automation_settings(
    payload: AutomationSettingsBase, db: SessionDep
) -> AutomationSettingsRead:
    return AutomationSettingsRead.model_validate(
        repo.upsert_automation_settings(db, payload)
    )


@router.get("/zac-sync-runs", response_model=list[ZacSyncRunRead])
def read_zac_runs(
    db: SessionDep,
    work_date: date | None = None,
    status: str | None = None,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
) -> list[ZacSyncRunRead]:
    runs = repo.list_zac_runs(db, work_date, status, oldest_first=order == "asc", limit=limit)
    return [ZacSyncRunRead.model_validate(run) for run in runs]


@router.post(
    "/zac-sync-runs", response_model=ZacSyncRunRead, status_code=status.HTTP_201_CREATED
)
def post_zac_run(payload: ZacSyncRunCreate, db: SessionDep) -> ZacSyncRunRead:
    return ZacSyncRunRead.model_validate(repo.create_zac_run(db, payload))


@router.post(
    "/zac-sync-runs/requests",
    response_model=ZacSyncRunRead,
    status_code=status.HTTP_201_CREATED,
)
def post_zac_run_request(payload: ZacRunRequestCreate, db: SessionDep) -> ZacSyncRunRead:
    return ZacSyncRunRead.model_validate(repo.request_zac_run(db, payload))


@router.patch("/zac-sync-runs/{run_id}", response_model=ZacSyncRunRead)
def patch_zac_run(run_id: str, payload: ZacSyncRunUpdate, db: SessionDep) -> ZacSyncRunRead:
    return ZacSyncRunRead.model_validate(repo.update_zac_run(db, run_id, payload))


@router.post("/zac-sync-runs/{run_id}/claim", response_model=ZacSyncRunRead)
def post_zac_run_claim(run_id: str, db: SessionDep) -> ZacSyncRunRead:
    return ZacSyncRunRead.model_validate(repo.claim_zac_run(db, run_id))


@router.post("/zac-sync-runs/{run_id}/cancel", response_model=ZacSyncRunRead)
def post_zac_run_cancel(run_id: str, db: SessionDep) -> ZacSyncRunRead:
    return ZacSyncRunRead.model_validate(repo.cancel_zac_run(db, run_id))


@router.get("/zac-work-kinds", response_model=list[ZacWorkKindRead])
def read_work_kinds(db: SessionDep, active: bool | None = None) -> list[ZacWorkKindRead]:
    return [ZacWorkKindRead.model_validate(kind) for kind in repo.list_work_kinds(db, active)]


@router.post("/zac-work-kinds", response_model=ZacWorkKindRead, status_code=status.HTTP_201_CREATED)
def post_work_kind(payload: ZacWorkKindCreate, db: SessionDep) -> ZacWorkKindRead:
    return ZacWorkKindRead.model_validate(repo.create_work_kind(db, payload))


@router.patch("/zac-work-kinds/{name}", response_model=ZacWorkKindRead)
def patch_work_kind(name: str, payload: ZacWorkKindUpdate, db: SessionDep) -> ZacWorkKindRead:
    return ZacWorkKindRead.model_validate(repo.update_work_kind(db, name, payload))


@router.get("/zac-sales-items", response_model=list[ZacSalesItemRead])
def read_sales_items(
    db: SessionDep, job_code: str | None = None, active: bool | None = None
) -> list[ZacSalesItemRead]:
    return [ZacSalesItemRead.model_validate(item) for item in repo.list_sales_items(db, job_code, active)]


@router.post(
    "/jobs/{code}/sales-items", response_model=ZacSalesItemRead, status_code=status.HTTP_201_CREATED
)
def post_sales_item(code: str, payload: ZacSalesItemCreate, db: SessionDep) -> ZacSalesItemRead:
    return ZacSalesItemRead.model_validate(repo.create_sales_item(db, code, payload))


@router.patch("/zac-sales-items/{item_id}", response_model=ZacSalesItemRead)
def patch_sales_item(item_id: str, payload: ZacSalesItemUpdate, db: SessionDep) -> ZacSalesItemRead:
    return ZacSalesItemRead.model_validate(repo.update_sales_item(db, item_id, payload))


@router.post("/zac-masters/import", response_model=ZacMasterImportResult)
def post_zac_masters_import(payload: ZacMasterImport, db: SessionDep) -> ZacMasterImportResult:
    return repo.import_zac_masters(db, payload)


@router.get("/zac-task-defaults", response_model=list[ZacTaskDefault])
def read_zac_task_defaults(db: SessionDep) -> list[ZacTaskDefault]:
    return repo.zac_task_defaults(db)


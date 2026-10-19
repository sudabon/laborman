from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

WorkStyle = Literal["office", "remote"]
ReportStatus = Literal[
    "not_started",
    "start_recorded",
    "start_mail_created",
    "end_recorded",
    "end_mail_created",
]
MailKind = Literal["start", "end"]
BreakSource = Literal["manual", "hr_mail"]
ZacSubmitMode = Literal["dry_run", "assist", "auto"]
EntryStyle = Literal["duration", "time_range"]
GapPolicy = Literal["block", "assign_default_job"]
ZacRunStatus = Literal[
    "requested",
    "cancelled",
    "running",
    "succeeded",
    "dry_run_done",
    "awaiting_user",
    "validation_failed",
    "needs_login",
    "vpn_unreachable",
    "hr_mail_not_found",
    "already_registered_in_zac",
    "failed",
]
# カレンダーの「要対応」にする最新の実行結果
ZAC_NEEDS_ACTION_STATUSES = frozenset(
    {"validation_failed", "needs_login", "failed", "already_registered_in_zac"}
)
ZacStatus = Literal["registered", "needs_action"]
AttendanceSource = Literal["hr_mail", "manual"]
AttendanceKind = Literal["work", "leave"]

NOTE_MAX_LENGTH = 600
TASK_DESCRIPTION_MAX_LENGTH = 200
JOB_CODE_MAX_LENGTH = 64
# 既定休憩の時刻。勤務日基準の 00:00〜29:59
WORK_TIME_PATTERN = r"^[0-2][0-9]:[0-5][0-9]$"

DEFAULT_START_SUBJECT_TEMPLATE = "【始業報告】{{date}}"
DEFAULT_START_BODY_TEMPLATE = """お疲れ様です。

本日、始業しました。

日付: {{date}}
始業時刻: {{start_time}}
勤務区分: {{work_style}}
メモ: {{note}}

よろしくお願いいたします。"""
DEFAULT_END_SUBJECT_TEMPLATE = "【終業報告】{{date}}"
DEFAULT_END_HEADER_TEMPLATE = "お疲れ様です。\n\n本日、終業しました。"
DEFAULT_END_BODY_TEMPLATE = """日付: {{date}}
始業時刻: {{start_time}}
終業時刻: {{end_time}}
勤務時間: {{work_duration}}
勤務区分: {{work_style}}
メモ: {{note}}

業務明細:
{{tasks}}"""
DEFAULT_END_FOOTER_TEMPLATE = "よろしくお願いいたします。"


class MailSettingsBase(BaseModel):
    boss_email: str = ""
    labor_ml_email: str = ""
    start_subject_template: str = DEFAULT_START_SUBJECT_TEMPLATE
    start_body_template: str = DEFAULT_START_BODY_TEMPLATE
    end_subject_template: str = DEFAULT_END_SUBJECT_TEMPLATE
    end_header_template: str = DEFAULT_END_HEADER_TEMPLATE
    end_body_template: str = DEFAULT_END_BODY_TEMPLATE
    end_footer_template: str = DEFAULT_END_FOOTER_TEMPLATE

    @field_validator("*", mode="before")
    @classmethod
    def none_to_empty_string(cls, value: object) -> object:
        return "" if value is None else value


class MailSettingsRead(MailSettingsBase):
    id: str = "default"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkReportUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)
    work_style: WorkStyle | None = None
    end_mail_body: str | None = None


class RecordEventRequest(WorkReportUpdate):
    pass


class MailCreatedRequest(BaseModel):
    kind: MailKind
    end_mail_body: str | None = None


class WorkReportRead(BaseModel):
    id: str
    work_date: date
    start_time: datetime | None = None
    end_time: datetime | None = None
    start_mail_created_at: datetime | None = None
    end_mail_created_at: datetime | None = None
    note: str = ""
    work_style: WorkStyle = "office"
    end_mail_body: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attendance_start_at: datetime | None = None
    attendance_end_at: datetime | None = None
    attendance_source: AttendanceSource | None = None
    attendance_kind: AttendanceKind = "work"
    attendance_imported_at: datetime | None = None
    zac_registered_at: datetime | None = None
    zac_status: ZacStatus | None = None
    status: ReportStatus
    work_duration_minutes: int | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "attendance_start_at",
        "attendance_end_at",
        "attendance_imported_at",
        "zac_registered_at",
    )
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class AttendanceUpdate(BaseModel):
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    source: AttendanceSource
    kind: AttendanceKind = "work"


class HealthRead(BaseModel):
    status: str


def ensure_utc(value: datetime | None) -> datetime | None:
    """SQLite はタイムゾーンを保持しないため、タイムゾーンなしの値は UTC とみなす。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


YEAR_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
WORK_KIND_MAX_LENGTH = 100


def blank_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class JobCreate(BaseModel):
    code: str = Field(min_length=1, max_length=JOB_CODE_MAX_LENGTH)
    name: str = Field(min_length=1)
    zac_search_text: str = ""
    zac_work_category: str = ""
    # 省略時は案件名の年月表記から導出する
    series_name: str | None = Field(default=None, max_length=200)
    valid_month: str | None = Field(default=None, pattern=YEAR_MONTH_PATTERN)

    @field_validator("series_name", "valid_month", mode="before")
    @classmethod
    def blank_series(cls, value: object) -> object:
        return blank_to_none(value)

    @field_validator("code", "name", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class JobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    zac_search_text: str | None = None
    zac_work_category: str | None = None
    # 空文字で解除する
    series_name: str | None = Field(default=None, max_length=200)
    valid_month: str | None = Field(default=None, pattern=YEAR_MONTH_PATTERN)
    is_active: bool | None = None

    @field_validator("series_name", "valid_month", mode="before")
    @classmethod
    def blank_series(cls, value: object) -> object:
        return blank_to_none(value)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class JobCodeChange(BaseModel):
    """ジョブ ID の変更。新しい ID のジョブを作り、元のジョブは無効化する（タスクは変えない）。"""

    code: str = Field(min_length=1, max_length=JOB_CODE_MAX_LENGTH)
    name: str | None = Field(default=None, min_length=1)
    zac_search_text: str | None = None
    zac_work_category: str | None = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class JobRead(BaseModel):
    code: str
    name: str
    zac_search_text: str
    zac_work_category: str
    series_name: str | None = None
    valid_month: str | None = None
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("last_used_at", "created_at", "updated_at")
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class TaskCreate(BaseModel):
    job_code: str = Field(min_length=1, max_length=JOB_CODE_MAX_LENGTH)
    description: str = Field(default="", max_length=TASK_DESCRIPTION_MAX_LENGTH)
    work_kind: str | None = Field(default=None, max_length=WORK_KIND_MAX_LENGTH)
    sales_item_id: str | None = None
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None

    @field_validator("work_kind", "sales_item_id", mode="before")
    @classmethod
    def blank_zac(cls, value: object) -> object:
        return blank_to_none(value)


class TaskUpdate(BaseModel):
    job_code: str | None = Field(
        default=None, min_length=1, max_length=JOB_CODE_MAX_LENGTH
    )
    description: str | None = Field(
        default=None, max_length=TASK_DESCRIPTION_MAX_LENGTH
    )
    # null・空文字で解除する
    work_kind: str | None = Field(default=None, max_length=WORK_KIND_MAX_LENGTH)
    sales_item_id: str | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None

    @field_validator("work_kind", "sales_item_id", mode="before")
    @classmethod
    def blank_zac(cls, value: object) -> object:
        return blank_to_none(value)


class TaskStartRequest(BaseModel):
    job_code: str = Field(min_length=1, max_length=JOB_CODE_MAX_LENGTH)
    description: str = Field(default="", max_length=TASK_DESCRIPTION_MAX_LENGTH)


class TaskRead(BaseModel):
    id: str
    work_report_id: str
    job_code: str
    description: str
    work_kind: str | None = None
    sales_item_id: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_at", "end_at", "created_at", "updated_at")
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class BreakCreate(BaseModel):
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None


class BreakUpdate(BaseModel):
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None


class BreakRead(BaseModel):
    id: str
    work_report_id: str
    start_at: datetime
    end_at: datetime | None = None
    source: BreakSource = "manual"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_at", "end_at", "created_at", "updated_at")
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class AutomationSettingsBase(BaseModel):
    default_break_start: str = Field(default="12:00", pattern=WORK_TIME_PATTERN)
    default_break_end: str = Field(default="13:00", pattern=WORK_TIME_PATTERN)
    hr_mail_from: str = ""
    hr_mail_subject_keyword: str = ""
    # zac 連携
    zac_submit_mode: ZacSubmitMode = "dry_run"
    entry_style: EntryStyle = "duration"
    time_unit_minutes: int = Field(default=15, ge=1, le=60)
    clip_tolerance_minutes: int = Field(default=15, ge=0, le=120)
    gap_policy: GapPolicy = "block"
    default_job_code: str | None = Field(default=None, max_length=JOB_CODE_MAX_LENGTH)
    default_work_kind: str | None = Field(default=None, max_length=WORK_KIND_MAX_LENGTH)
    default_sales_item_id: str | None = None
    description_max_length: int = Field(default=100, ge=1, le=1000)

    @field_validator("hr_mail_from", "hr_mail_subject_keyword", mode="before")
    @classmethod
    def strip_hr_mail_text(cls, value: object) -> object:
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value

    @field_validator("default_job_code", "default_work_kind", "default_sales_item_id", mode="before")
    @classmethod
    def blank_job_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("time_unit_minutes")
    @classmethod
    def divides_hour(cls, value: int) -> int:
        if 60 % value != 0:
            raise ValueError("丸め単位は 60 の約数（1・5・10・15・30・60 など）にしてください")
        return value

    @model_validator(mode="after")
    def end_after_start(self) -> AutomationSettingsBase:
        if self.default_break_end <= self.default_break_start:
            raise ValueError("既定休憩の終了は開始より後にしてください")
        if self.gap_policy == "assign_default_job" and not (
            self.default_job_code and self.default_work_kind and self.default_sales_item_id
        ):
            raise ValueError(
                "空き時間を既定ジョブに割り当てる場合は既定ジョブ・作業内容・売上項目を指定してください"
            )
        return self


class AutomationSettingsRead(AutomationSettingsBase):
    id: str = "default"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---- zac 登録ドラフト ----

IssueSeverity = Literal["error", "warning", "info"]


class ZacDraftAttendance(BaseModel):
    start: str  # 勤務日基準の HH:MM
    end: str
    source: str | None = None


class ZacDraftBreak(BaseModel):
    start: str
    end: str


class ZacDraftEntry(BaseModel):
    job_code: str
    zac_search_text: str
    project_name: str
    work_kind: str
    sales_item: str
    minutes: int
    description: str
    # time_range のときだけ入る
    start: str | None = None
    end: str | None = None


class ZacDraftIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    ref_id: str | None = None


class ZacDraftRead(BaseModel):
    work_date: date
    attendance: ZacDraftAttendance | None = None
    breaks: list[ZacDraftBreak]
    working_minutes: int | None = None
    entry_style: EntryStyle
    entries: list[ZacDraftEntry]
    issues: list[ZacDraftIssue]
    registrable: bool
    auto_allowed: bool
    zac_registered_at: datetime | None = None

    @field_validator("zac_registered_at")
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


# ---- zac 連携の実行履歴 ----


class ZacSyncRunCreate(BaseModel):
    work_date: date
    mode: ZacSubmitMode
    agent_version: str | None = Field(default=None, max_length=32)


class ZacSyncRunUpdate(BaseModel):
    status: ZacRunStatus | None = None
    mode: ZacSubmitMode | None = None
    message: str | None = None
    entries: list[Any] | dict[str, Any] | None = None
    screenshot_path: str | None = None
    agent_version: str | None = Field(default=None, max_length=32)

    @field_validator("status")
    @classmethod
    def not_request_states(cls, value: str | None) -> str | None:
        if value in ("requested", "cancelled"):
            raise ValueError("依頼・取り消しは専用の API で行ってください")
        return value


class ZacRunRequestCreate(BaseModel):
    work_date: date


class ZacSyncRunRead(BaseModel):
    id: str
    work_date: date
    mode: ZacSubmitMode
    status: ZacRunStatus
    entries: list[Any] | dict[str, Any] | None = None
    message: str | None = None
    screenshot_path: str | None = None
    agent_version: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("started_at", "finished_at")
    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


# ---- zac の作業内容・売上項目 ----


class ZacWorkKindCreate(BaseModel):
    name: str = Field(min_length=1, max_length=WORK_KIND_MAX_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ZacWorkKindUpdate(BaseModel):
    is_active: bool | None = None
    sort_order: int | None = None


class ZacWorkKindRead(BaseModel):
    name: str
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ZacSalesItemCreate(BaseModel):
    name: str = Field(min_length=1)
    is_closed: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ZacSalesItemUpdate(BaseModel):
    is_active: bool | None = None
    is_closed: bool | None = None
    sort_order: int | None = None


class ZacSalesItemRead(BaseModel):
    id: str
    job_code: str
    name: str
    valid_month: str | None = None
    is_closed: bool
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ZacMasterSalesItem(BaseModel):
    name: str = Field(min_length=1)
    is_closed: bool = False


class ZacMasterProject(BaseModel):
    code: str = Field(min_length=1, max_length=JOB_CODE_MAX_LENGTH)
    name: str = Field(min_length=1)
    sales_items: list[ZacMasterSalesItem] = []


class ZacMasterImport(BaseModel):
    """zac から読み取った（または画面で記録した）選択肢。追加・更新だけを行う。"""

    work_kinds: list[str] = []
    projects: list[ZacMasterProject] = []
    # 読み取りに使った日の月（YYYY-MM）。これより前の月の案件は取り込まない（zac の候補に過去月が残るため）
    as_of_month: str | None = Field(default=None, pattern=YEAR_MONTH_PATTERN)


class ZacMasterImportCounts(BaseModel):
    work_kinds: int = 0
    jobs: int = 0
    sales_items: int = 0


class ZacMasterImportResult(BaseModel):
    created: ZacMasterImportCounts
    updated: ZacMasterImportCounts
    # 有効なジョブのうち、今回の取込に現れなかったもの（自動では無効化しない）
    missing_jobs: list[str]
    # 対象年月が as_of_month より前のため取り込まなかった案件
    skipped_jobs: list[str] = []


class ZacTaskDefault(BaseModel):
    """ジョブごとに直近のタスクで使った作業内容・売上項目（業務明細の初期値に使う）。"""

    job_code: str
    work_kind: str | None = None
    sales_item_id: str | None = None


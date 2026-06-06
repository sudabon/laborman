from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkStyle = Literal["office", "remote"]
ReportStatus = Literal[
    "not_started",
    "start_recorded",
    "start_mail_created",
    "end_recorded",
    "end_mail_created",
]
MailKind = Literal["start", "end"]

NOTE_MAX_LENGTH = 600

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
メモ: {{note}}"""
DEFAULT_END_FOOTER_TEMPLATE = "よろしくお願いいたします。"


class MailSettingsBase(BaseModel):
    boss_email: str = ""
    labor_ml_email: str = ""
    cc_emails: str = ""
    bcc_emails: str = ""
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
    status: ReportStatus
    work_duration_minutes: int | None = None

    model_config = ConfigDict(from_attributes=True)


class HealthRead(BaseModel):
    status: str

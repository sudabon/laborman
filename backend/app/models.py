from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def uuid_str() -> str:
    return str(uuid.uuid4())


class MailSettings(Base):
    __tablename__ = "mail_settings"
    __table_args__ = (
        CheckConstraint("id = 'default'", name="ck_mail_settings_single_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    boss_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    labor_ml_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    start_subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    start_body_template: Mapped[str] = mapped_column(Text, nullable=False)
    end_subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    end_header_template: Mapped[str] = mapped_column(Text, nullable=False)
    end_body_template: Mapped[str] = mapped_column(Text, nullable=False)
    end_footer_template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkReport(Base):
    __tablename__ = "work_reports"
    __table_args__ = (
        UniqueConstraint("work_date", name="uq_work_reports_work_date"),
        CheckConstraint(
            "work_style in ('office', 'remote')", name="ck_work_reports_work_style"
        ),
        CheckConstraint(
            "attendance_source IS NULL OR attendance_source in ('hr_mail', 'manual')",
            name="ck_work_reports_attendance_source",
        ),
        CheckConstraint(
            "attendance_kind in ('work', 'leave')",
            name="ck_work_reports_attendance_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_mail_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_mail_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    work_style: Mapped[str] = mapped_column(
        String(16), default="office", nullable=False
    )
    end_mail_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 出退勤実績（人事メール由来または手入力）。打刻（start_time / end_time）とは別
    attendance_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attendance_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attendance_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attendance_kind: Mapped[str] = mapped_column(
        String(16), default="work", server_default="work", nullable=False
    )
    attendance_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # zac への保存成功日時（実行履歴が succeeded になったとき設定する）
    zac_registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tasks: Mapped[list[WorkTask]] = relationship(
        back_populates="work_report", cascade="all, delete-orphan"
    )
    breaks: Mapped[list[WorkBreak]] = relationship(
        back_populates="work_report", cascade="all, delete-orphan"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Job(Base):
    __tablename__ = "jobs"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    zac_search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # zac の作業登録で使う既定の作業内容
    zac_work_category: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 月ごとに JOB 番号が変わる案件は、シリーズ名と対象年月（YYYY-MM）を持つ
    series_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkTask(Base):
    __tablename__ = "work_tasks"
    __table_args__ = (
        CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_work_tasks_end_after_start"
        ),
        # 進行中（end_at IS NULL）のタスクは勤務日ごとに 1 件まで
        Index(
            "uq_work_tasks_running",
            "work_report_id",
            unique=True,
            postgresql_where=text("end_at IS NULL"),
            sqlite_where=text("end_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    work_report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("work_reports.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    job_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("jobs.code", onupdate="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # zac の作業内容・売上項目（未設定は zac 登録のドラフトで error）
    work_kind: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("zac_work_kinds.name", onupdate="CASCADE"), nullable=True
    )
    sales_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("zac_sales_items.id"), nullable=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    work_report: Mapped[WorkReport] = relationship(back_populates="tasks")
    sales_item: Mapped[ZacSalesItem | None] = relationship()


class WorkBreak(Base):
    __tablename__ = "work_breaks"
    __table_args__ = (
        CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_work_breaks_end_after_start"
        ),
        CheckConstraint(
            "source in ('manual', 'hr_mail')", name="ck_work_breaks_source"
        ),
        # 進行中（end_at IS NULL）の休憩は勤務日ごとに 1 件まで
        Index(
            "uq_work_breaks_running",
            "work_report_id",
            unique=True,
            postgresql_where=text("end_at IS NULL"),
            sqlite_where=text("end_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    work_report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("work_reports.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    work_report: Mapped[WorkReport] = relationship(back_populates="breaks")


class AutomationSettings(Base):
    __tablename__ = "automation_settings"
    __table_args__ = (
        CheckConstraint("id = 'default'", name="ck_automation_settings_single_row"),
        CheckConstraint(
            "zac_submit_mode in ('dry_run', 'assist', 'auto')",
            name="ck_automation_settings_zac_submit_mode",
        ),
        CheckConstraint(
            "entry_style in ('duration', 'time_range')",
            name="ck_automation_settings_entry_style",
        ),
        CheckConstraint(
            "time_unit_minutes between 1 and 60 and 60 % time_unit_minutes = 0",
            name="ck_automation_settings_time_unit_minutes",
        ),
        CheckConstraint(
            "clip_tolerance_minutes >= 0",
            name="ck_automation_settings_clip_tolerance_minutes",
        ),
        CheckConstraint(
            "gap_policy in ('block', 'assign_default_job')",
            name="ck_automation_settings_gap_policy",
        ),
        CheckConstraint(
            "description_max_length >= 1",
            name="ck_automation_settings_description_max_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    default_break_start: Mapped[str] = mapped_column(
        String(5), default="12:00", server_default="12:00", nullable=False
    )
    default_break_end: Mapped[str] = mapped_column(
        String(5), default="13:00", server_default="13:00", nullable=False
    )
    # 人事メールの検索条件。差出人は任意（空なら差出人で絞り込まない）
    hr_mail_from: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    hr_mail_subject_keyword: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    # zac 連携
    zac_submit_mode: Mapped[str] = mapped_column(
        String(16), default="dry_run", server_default="dry_run", nullable=False
    )
    entry_style: Mapped[str] = mapped_column(
        String(16), default="duration", server_default="duration", nullable=False
    )
    time_unit_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15", nullable=False
    )
    clip_tolerance_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15", nullable=False
    )
    gap_policy: Mapped[str] = mapped_column(
        String(32), default="block", server_default="block", nullable=False
    )
    default_job_code: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("jobs.code", onupdate="CASCADE"), nullable=True
    )
    description_max_length: Mapped[int] = mapped_column(
        Integer, default=100, server_default="100", nullable=False
    )
    # 空き時間を既定ジョブに割り当てるときの作業内容・売上項目
    default_work_kind: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("zac_work_kinds.name", onupdate="CASCADE"), nullable=True
    )
    default_sales_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("zac_sales_items.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ZacWorkKind(Base):
    """zac の作業内容の選択肢（プロジェクト作業・プロジェクト関連打ち合わせ など）。"""

    __tablename__ = "zac_work_kinds"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ZacSalesItem(Base):
    """zac の案件ごとの売上項目の選択肢。"""

    __tablename__ = "zac_sales_items"
    __table_args__ = (
        UniqueConstraint("job_code", "name", name="uq_zac_sales_items_job_code_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("jobs.code", onupdate="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 名前の年月表記から読み取った対象年月（YYYY-MM）。作業の種類を表す項目は NULL
    valid_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # zac で「売上計上済」の印がある
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


ZAC_RUN_STATUSES = (
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
)


class ZacSyncRun(Base):
    """zac 連携の実行履歴。画面からの実行依頼（requested）のキューも兼ねる。"""

    __tablename__ = "zac_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "mode in ('dry_run', 'assist', 'auto')", name="ck_zac_sync_runs_mode"
        ),
        CheckConstraint(
            "status in ("
            + ", ".join(f"'{status}'" for status in ZAC_RUN_STATUSES)
            + ")",
            name="ck_zac_sync_runs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    entries: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


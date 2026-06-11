from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

"""add attendance records and hr mail search settings

Revision ID: 20261013_0001
Revises: 20261012_0001
Create Date: 2026-10-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261013_0001"
down_revision = "20261012_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_reports",
        sa.Column("attendance_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_reports",
        sa.Column("attendance_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_reports",
        sa.Column("attendance_source", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "work_reports",
        sa.Column(
            "attendance_kind",
            sa.String(length=16),
            nullable=False,
            server_default="work",
        ),
    )
    op.add_column(
        "work_reports",
        sa.Column("attendance_imported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_work_reports_attendance_source",
        "work_reports",
        "attendance_source IS NULL OR attendance_source in ('hr_mail', 'manual')",
    )
    op.create_check_constraint(
        "ck_work_reports_attendance_kind",
        "work_reports",
        "attendance_kind in ('work', 'leave')",
    )

    op.add_column(
        "automation_settings",
        sa.Column("hr_mail_from", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "automation_settings",
        sa.Column(
            "hr_mail_subject_keyword", sa.Text(), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("automation_settings", "hr_mail_subject_keyword")
    op.drop_column("automation_settings", "hr_mail_from")
    op.drop_constraint(
        "ck_work_reports_attendance_kind", "work_reports", type_="check"
    )
    op.drop_constraint(
        "ck_work_reports_attendance_source", "work_reports", type_="check"
    )
    op.drop_column("work_reports", "attendance_imported_at")
    op.drop_column("work_reports", "attendance_kind")
    op.drop_column("work_reports", "attendance_source")
    op.drop_column("work_reports", "attendance_end_at")
    op.drop_column("work_reports", "attendance_start_at")

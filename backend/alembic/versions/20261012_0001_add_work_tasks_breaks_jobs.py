"""add work tasks, breaks, jobs and automation settings

Revision ID: 20261012_0001
Revises: 20260611_0001
Create Date: 2026-10-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261012_0001"
down_revision = "20260611_0001"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("zac_search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("zac_work_category", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "work_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_report_id", sa.String(length=36), nullable=False),
        sa.Column("job_code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["work_report_id"], ["work_reports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_code"], ["jobs.code"], onupdate="CASCADE"),
        sa.CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_work_tasks_end_after_start"
        ),
    )
    op.create_index(
        "ix_work_tasks_work_report_id", "work_tasks", ["work_report_id"]
    )
    op.create_index(
        "uq_work_tasks_running",
        "work_tasks",
        ["work_report_id"],
        unique=True,
        postgresql_where=sa.text("end_at IS NULL"),
    )

    op.create_table(
        "work_breaks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_report_id", sa.String(length=36), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="manual"
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["work_report_id"], ["work_reports.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "end_at IS NULL OR end_at > start_at",
            name="ck_work_breaks_end_after_start",
        ),
        sa.CheckConstraint(
            "source in ('manual', 'hr_mail')", name="ck_work_breaks_source"
        ),
    )
    op.create_index(
        "ix_work_breaks_work_report_id", "work_breaks", ["work_report_id"]
    )
    op.create_index(
        "uq_work_breaks_running",
        "work_breaks",
        ["work_report_id"],
        unique=True,
        postgresql_where=sa.text("end_at IS NULL"),
    )

    op.create_table(
        "automation_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "default_break_start",
            sa.String(length=5),
            nullable=False,
            server_default="12:00",
        ),
        sa.Column(
            "default_break_end",
            sa.String(length=5),
            nullable=False,
            server_default="13:00",
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 'default'", name="ck_automation_settings_single_row"),
    )


def downgrade() -> None:
    op.drop_table("automation_settings")
    op.drop_index("uq_work_breaks_running", table_name="work_breaks")
    op.drop_index("ix_work_breaks_work_report_id", table_name="work_breaks")
    op.drop_table("work_breaks")
    op.drop_index("uq_work_tasks_running", table_name="work_tasks")
    op.drop_index("ix_work_tasks_work_report_id", table_name="work_tasks")
    op.drop_table("work_tasks")
    op.drop_table("jobs")

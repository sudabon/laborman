"""add zac settings, zac_registered_at and zac_sync_runs

Revision ID: 20261013_0002
Revises: 20261013_0001
Create Date: 2026-10-13 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261013_0002"
down_revision = "20261013_0001"
branch_labels = None
depends_on = None

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


def upgrade() -> None:
    op.add_column(
        "work_reports",
        sa.Column("zac_registered_at", sa.DateTime(timezone=True), nullable=True),
    )

    columns = [
        sa.Column("zac_submit_mode", sa.String(length=16), nullable=False, server_default="dry_run"),
        sa.Column("entry_style", sa.String(length=16), nullable=False, server_default="duration"),
        sa.Column("time_unit_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("clip_tolerance_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("gap_policy", sa.String(length=32), nullable=False, server_default="block"),
        sa.Column("default_job_code", sa.String(length=64), nullable=True),
        sa.Column("description_max_length", sa.Integer(), nullable=False, server_default="100"),
    ]
    for column in columns:
        op.add_column("automation_settings", column)
    op.create_foreign_key(
        "fk_automation_settings_default_job_code",
        "automation_settings",
        "jobs",
        ["default_job_code"],
        ["code"],
        onupdate="CASCADE",
    )
    checks = {
        "ck_automation_settings_zac_submit_mode": "zac_submit_mode in ('dry_run', 'assist', 'auto')",
        "ck_automation_settings_entry_style": "entry_style in ('duration', 'time_range')",
        "ck_automation_settings_time_unit_minutes": (
            "time_unit_minutes between 1 and 60 and 60 % time_unit_minutes = 0"
        ),
        "ck_automation_settings_clip_tolerance_minutes": "clip_tolerance_minutes >= 0",
        "ck_automation_settings_gap_policy": "gap_policy in ('block', 'assign_default_job')",
        "ck_automation_settings_description_max_length": "description_max_length >= 1",
    }
    for name, condition in checks.items():
        op.create_check_constraint(name, "automation_settings", condition)

    op.create_table(
        "zac_sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("screenshot_path", sa.Text(), nullable=True),
        sa.Column("agent_version", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("mode in ('dry_run', 'assist', 'auto')", name="ck_zac_sync_runs_mode"),
        sa.CheckConstraint(
            "status in (" + ", ".join(f"'{status}'" for status in ZAC_RUN_STATUSES) + ")",
            name="ck_zac_sync_runs_status",
        ),
    )
    op.create_index("ix_zac_sync_runs_work_date", "zac_sync_runs", ["work_date"])


def downgrade() -> None:
    op.drop_index("ix_zac_sync_runs_work_date", table_name="zac_sync_runs")
    op.drop_table("zac_sync_runs")
    for name in (
        "ck_automation_settings_description_max_length",
        "ck_automation_settings_gap_policy",
        "ck_automation_settings_clip_tolerance_minutes",
        "ck_automation_settings_time_unit_minutes",
        "ck_automation_settings_entry_style",
        "ck_automation_settings_zac_submit_mode",
    ):
        op.drop_constraint(name, "automation_settings", type_="check")
    op.drop_constraint(
        "fk_automation_settings_default_job_code", "automation_settings", type_="foreignkey"
    )
    for column in (
        "description_max_length",
        "default_job_code",
        "gap_policy",
        "clip_tolerance_minutes",
        "time_unit_minutes",
        "entry_style",
        "zac_submit_mode",
    ):
        op.drop_column("automation_settings", column)
    op.drop_column("work_reports", "zac_registered_at")

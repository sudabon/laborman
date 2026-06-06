"""create labor report tables

Revision ID: 20260606_0001
Revises:
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260606_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("boss_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("labor_ml_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("cc_emails", sa.Text(), nullable=False, server_default=""),
        sa.Column("bcc_emails", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_subject_template", sa.Text(), nullable=False),
        sa.Column("start_body_template", sa.Text(), nullable=False),
        sa.Column("end_subject_template", sa.Text(), nullable=False),
        sa.Column("end_header_template", sa.Text(), nullable=False),
        sa.Column("end_body_template", sa.Text(), nullable=False),
        sa.Column("end_footer_template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 'default'", name="ck_mail_settings_single_row"),
    )

    op.create_table(
        "work_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_mail_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_mail_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("work_style", sa.String(length=16), nullable=False, server_default="office"),
        sa.Column("end_mail_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_date", name="uq_work_reports_work_date"),
        sa.CheckConstraint("work_style in ('office', 'remote')", name="ck_work_reports_work_style"),
    )
    op.create_index("ix_work_reports_work_date", "work_reports", ["work_date"])


def downgrade() -> None:
    op.drop_index("ix_work_reports_work_date", table_name="work_reports")
    op.drop_table("work_reports")
    op.drop_table("mail_settings")

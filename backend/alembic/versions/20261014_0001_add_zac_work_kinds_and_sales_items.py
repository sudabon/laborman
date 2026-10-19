"""add zac work kinds, sales items, task zac attributes and job series

Revision ID: 20261014_0001
Revises: 20261013_0002
Create Date: 2026-10-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261014_0001"
down_revision = "20261013_0002"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "zac_work_kinds",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "zac_sales_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("valid_month", sa.String(length=7), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_code"], ["jobs.code"], onupdate="CASCADE"),
        sa.UniqueConstraint("job_code", "name", name="uq_zac_sales_items_job_code_name"),
    )
    op.create_index("ix_zac_sales_items_job_code", "zac_sales_items", ["job_code"])

    op.add_column("jobs", sa.Column("series_name", sa.String(length=200), nullable=True))
    op.add_column("jobs", sa.Column("valid_month", sa.String(length=7), nullable=True))

    op.add_column("work_tasks", sa.Column("work_kind", sa.String(length=100), nullable=True))
    op.add_column("work_tasks", sa.Column("sales_item_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_work_tasks_work_kind", "work_tasks", "zac_work_kinds", ["work_kind"], ["name"], onupdate="CASCADE"
    )
    op.create_foreign_key(
        "fk_work_tasks_sales_item_id", "work_tasks", "zac_sales_items", ["sales_item_id"], ["id"]
    )

    op.add_column("automation_settings", sa.Column("default_work_kind", sa.String(length=100), nullable=True))
    op.add_column("automation_settings", sa.Column("default_sales_item_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_automation_settings_default_work_kind",
        "automation_settings",
        "zac_work_kinds",
        ["default_work_kind"],
        ["name"],
        onupdate="CASCADE",
    )
    op.create_foreign_key(
        "fk_automation_settings_default_sales_item_id",
        "automation_settings",
        "zac_sales_items",
        ["default_sales_item_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_automation_settings_default_sales_item_id", "automation_settings", type_="foreignkey")
    op.drop_constraint("fk_automation_settings_default_work_kind", "automation_settings", type_="foreignkey")
    op.drop_column("automation_settings", "default_sales_item_id")
    op.drop_column("automation_settings", "default_work_kind")
    op.drop_constraint("fk_work_tasks_sales_item_id", "work_tasks", type_="foreignkey")
    op.drop_constraint("fk_work_tasks_work_kind", "work_tasks", type_="foreignkey")
    op.drop_column("work_tasks", "sales_item_id")
    op.drop_column("work_tasks", "work_kind")
    op.drop_column("jobs", "valid_month")
    op.drop_column("jobs", "series_name")
    op.drop_index("ix_zac_sales_items_job_code", table_name="zac_sales_items")
    op.drop_table("zac_sales_items")
    op.drop_table("zac_work_kinds")

"""drop automation settings time_unit_minutes (zac の工数は丸めずに入力する)

Revision ID: 20261119_0001
Revises: 20261014_0001
Create Date: 2026-11-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261119_0001"
down_revision = "20261014_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_automation_settings_time_unit_minutes", "automation_settings", type_="check"
    )
    op.drop_column("automation_settings", "time_unit_minutes")


def downgrade() -> None:
    op.add_column(
        "automation_settings",
        sa.Column("time_unit_minutes", sa.Integer(), nullable=False, server_default="15"),
    )
    op.create_check_constraint(
        "ck_automation_settings_time_unit_minutes",
        "automation_settings",
        "time_unit_minutes between 1 and 60 and 60 % time_unit_minutes = 0",
    )

"""drop mail settings cc and bcc columns

Revision ID: 20260611_0001
Revises: 20260606_0001
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260611_0001"
down_revision = "20260606_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("mail_settings", "bcc_emails")
    op.drop_column("mail_settings", "cc_emails")


def downgrade() -> None:
    op.add_column(
        "mail_settings",
        sa.Column("cc_emails", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "mail_settings",
        sa.Column("bcc_emails", sa.Text(), nullable=False, server_default=""),
    )

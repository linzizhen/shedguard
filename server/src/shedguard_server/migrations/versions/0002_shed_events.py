"""建立 shed_events 表。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shed_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("event_date", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.String(length=40), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("device_id", "event_date", name="uq_shed_events_device_date"),
    )
    op.create_index("ix_shed_events_event_date", "shed_events", ["event_date"])


def downgrade() -> None:
    op.drop_index("ix_shed_events_event_date", table_name="shed_events")
    op.drop_table("shed_events")
"""建立 shedding_states 表。

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shedding_states",
        sa.Column("image_id", sa.String(length=36), primary_key=True),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("local_date", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("probabilities_json", sa.Text(), nullable=True),
        sa.Column("detector_name", sa.String(length=64), nullable=False),
        sa.Column("classifier_name", sa.String(length=64), nullable=False),
        sa.Column("box_json", sa.Text(), nullable=True),
        sa.Column("computed_at_utc", sa.String(length=40), nullable=False),
        sa.Column("state_version", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], name="fk_shedding_states_image_id"),
    )
    op.create_index(
        "ix_shedding_states_device_date", "shedding_states", ["device_id", "local_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_shedding_states_device_date", table_name="shedding_states")
    op.drop_table("shedding_states")

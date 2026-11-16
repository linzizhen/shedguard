"""摄像头接入层：cameras 表

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("last_frame_at_utc", sa.String(40), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
    )
    op.create_index("ix_cameras_owner_id", "cameras", ["owner_id"])
    op.create_index("ix_cameras_pet_id", "cameras", ["pet_id"])


def downgrade() -> None:
    op.drop_index("ix_cameras_pet_id", table_name="cameras")
    op.drop_index("ix_cameras_owner_id", table_name="cameras")
    op.drop_table("cameras")
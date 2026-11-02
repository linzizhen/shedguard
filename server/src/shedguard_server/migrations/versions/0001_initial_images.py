"""建立 images 表。

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("rel_path", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("captured_at_utc", sa.String(length=40), nullable=False),
        sa.Column("local_date", sa.String(length=10), nullable=False),
        sa.Column("received_at_utc", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("rel_path", name="uq_images_rel_path"),
        sa.UniqueConstraint("sha256", name="uq_images_sha256"),
    )
    op.create_index("ix_images_device_id", "images", ["device_id"])
    op.create_index("ix_images_sha256", "images", ["sha256"])
    op.create_index("ix_images_local_date", "images", ["local_date"])
    op.create_index(
        "ix_images_date_device_captured",
        "images",
        ["local_date", "device_id", "captured_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_images_date_device_captured", table_name="images")
    op.drop_index("ix_images_local_date", table_name="images")
    op.drop_index("ix_images_sha256", table_name="images")
    op.drop_index("ix_images_device_id", table_name="images")
    op.drop_table("images")
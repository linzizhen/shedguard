"""建立 frame_metrics 表。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frame_metrics",
        sa.Column("image_id", sa.String(length=36), primary_key=True),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("local_date", sa.String(length=10), nullable=False),
        sa.Column("detected", sa.Integer(), nullable=False),
        sa.Column("box_json", sa.Text(), nullable=True),
        sa.Column("detector_name", sa.String(length=64), nullable=False),
        sa.Column("detector_confidence", sa.Float(), nullable=True),
        sa.Column("normalized", sa.Integer(), nullable=False),
        sa.Column("exposure_scale", sa.Float(), nullable=False),
        sa.Column("lightness_mean", sa.Float(), nullable=True),
        sa.Column("lightness_std", sa.Float(), nullable=True),
        sa.Column("saturation_mean", sa.Float(), nullable=True),
        sa.Column("high_light_ratio", sa.Float(), nullable=True),
        sa.Column("edge_density", sa.Float(), nullable=True),
        sa.Column("color_entropy", sa.Float(), nullable=True),
        sa.Column("background_lightness", sa.Float(), nullable=True),
        sa.Column("computed_at_utc", sa.String(length=40), nullable=False),
        sa.Column("metrics_version", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], name="fk_frame_metrics_image_id"),
    )
    op.create_index("ix_frame_metrics_device_date", "frame_metrics", ["device_id", "local_date"])


def downgrade() -> None:
    op.drop_index("ix_frame_metrics_device_date", table_name="frame_metrics")
    op.drop_table("frame_metrics")
"""萌照三张表：设置、成品、反馈。

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.create_table(
        "portrait_settings",
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("per_day", sa.Integer(), nullable=False),
        sa.Column("start_hour", sa.Integer(), nullable=False),
        sa.Column("end_hour", sa.Integer(), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
    )

    op.create_table(
        "portrait_shots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column(
            "source_image_id", sa.String(36), sa.ForeignKey("images.id"), nullable=True
        ),
        sa.Column("rel_path", sa.String(255), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("dhash", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "device_id", "local_date", "slot", name="ux_portrait_shots_device_date_slot"
        ),
    )
    op.create_index("ix_portrait_shots_device_id", "portrait_shots", ["device_id"])
    op.create_index("ix_portrait_shots_pet_id", "portrait_shots", ["pet_id"])
    op.create_index("ix_portrait_shots_pet_date", "portrait_shots", ["pet_id", "local_date"])

    op.create_table(
        "portrait_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "shot_id", sa.String(36), sa.ForeignKey("portrait_shots.id"), nullable=False
        ),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("crop_box", sa.String(64), nullable=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.UniqueConstraint("shot_id", "kind", name="ux_portrait_feedback_shot_kind"),
    )
    op.create_index("ix_portrait_feedback_shot_id", "portrait_feedback", ["shot_id"])
    op.create_index("ix_portrait_feedback_owner_id", "portrait_feedback", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_portrait_feedback_owner_id", table_name="portrait_feedback")
    op.drop_index("ix_portrait_feedback_shot_id", table_name="portrait_feedback")
    op.drop_table("portrait_feedback")
    op.drop_index("ix_portrait_shots_pet_date", table_name="portrait_shots")
    op.drop_index("ix_portrait_shots_pet_id", table_name="portrait_shots")
    op.drop_index("ix_portrait_shots_device_id", table_name="portrait_shots")
    op.drop_table("portrait_shots")
    op.drop_table("portrait_settings")
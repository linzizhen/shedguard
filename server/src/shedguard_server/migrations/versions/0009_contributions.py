"""数据贡献三张表：用户偏好、待分享样本、本地打包留档。

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.create_table(
        "contribution_settings",
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("include_full", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
    )

    op.create_table(
        "contribution_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column(
            "source_image_id", sa.String(36), sa.ForeignKey("images.id"), nullable=False
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("crop_rel_path", sa.String(255), nullable=False),
        sa.Column("full_rel_path", sa.String(255), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("upload_status", sa.String(16), nullable=False),
        sa.Column("upload_attempts", sa.Integer(), nullable=False),
        sa.Column("remote_crop_path", sa.String(255), nullable=True),
        sa.Column("remote_full_path", sa.String(255), nullable=True),
        sa.Column("uploaded_at_utc", sa.String(40), nullable=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "source_image_id", "owner_id", name="ux_contribution_samples_image_owner"
        ),
    )
    op.create_index("ix_contribution_samples_owner_id", "contribution_samples", ["owner_id"])
    op.create_index("ix_contribution_samples_device_id", "contribution_samples", ["device_id"])
    op.create_index("ix_contribution_samples_local_date", "contribution_samples", ["local_date"])

    op.create_table(
        "contribution_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(128), nullable=False),
        sa.Column("rel_path", sa.String(255), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
    )
    op.create_index("ix_contribution_exports_owner_id", "contribution_exports", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_contribution_exports_owner_id", table_name="contribution_exports")
    op.drop_table("contribution_exports")
    op.drop_index("ix_contribution_samples_local_date", table_name="contribution_samples")
    op.drop_index("ix_contribution_samples_device_id", table_name="contribution_samples")
    op.drop_index("ix_contribution_samples_owner_id", table_name="contribution_samples")
    op.drop_table("contribution_samples")
    op.drop_table("contribution_settings")

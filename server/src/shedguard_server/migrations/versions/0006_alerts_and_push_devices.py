"""alerts 与 push_devices 表。

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("expo_push_token", sa.String(255), nullable=False, unique=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
    )
    op.create_index("ix_push_devices_device_id", "push_devices", ["device_id"])
    op.create_index("ix_push_devices_pet_id", "push_devices", ["pet_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("images.id"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("delivered_at_utc", sa.String(40), nullable=True),
        sa.Column("read_at_utc", sa.String(40), nullable=True),
        sa.Column("push_status", sa.String(16), nullable=False),
        sa.UniqueConstraint(
            "device_id", "local_date", "kind", name="ux_alerts_device_date_kind"
        ),
    )
    op.create_index("ix_alerts_device_id", "alerts", ["device_id"])
    op.create_index("ix_alerts_pet_id", "alerts", ["pet_id"])
    op.create_index("ix_alerts_device_date", "alerts", ["device_id", "local_date"])


def downgrade() -> None:
    op.drop_index("ix_alerts_device_date", table_name="alerts")
    op.drop_index("ix_alerts_pet_id", table_name="alerts")
    op.drop_index("ix_alerts_device_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_push_devices_pet_id", table_name="push_devices")
    op.drop_index("ix_push_devices_device_id", table_name="push_devices")
    op.drop_table("push_devices")

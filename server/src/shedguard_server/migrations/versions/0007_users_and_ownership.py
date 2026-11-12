"""users 表与资源归属（pets.owner_id、push_devices.owner_id）。

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"

#: 迁移前历史数据的归属占位账号；token_hash 为空，任何令牌都匹配不到它。
LEGACY_OWNER_ID = "legacy"
LEGACY_CREATED_AT = "2026-11-12T00:00:00+00:00"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("last_seen_at_utc", sa.String(40), nullable=True),
    )
    op.execute(
        sa.text(
            "INSERT INTO users (id, token_hash, created_at_utc) "
            "VALUES (:id, :token_hash, :created)"
        ).bindparams(
            id=LEGACY_OWNER_ID, token_hash="", created=LEGACY_CREATED_AT
        )
    )

    # 历史宠物统一挂到 legacy 账号下；server_default 兼容 SQLite 的 ADD COLUMN。
    op.add_column(
        "pets",
        sa.Column("owner_id", sa.String(36), nullable=False, server_default=LEGACY_OWNER_ID),
    )
    op.create_index("ix_pets_owner_id", "pets", ["owner_id"])

    op.add_column("push_devices", sa.Column("owner_id", sa.String(36), nullable=True))
    op.create_index("ix_push_devices_owner_id", "push_devices", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_push_devices_owner_id", table_name="push_devices")
    op.drop_column("push_devices", "owner_id")
    op.drop_index("ix_pets_owner_id", table_name="pets")
    op.drop_column("pets", "owner_id")
    op.drop_table("users")

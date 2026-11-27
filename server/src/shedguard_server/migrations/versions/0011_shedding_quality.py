"""输入质量门：shedding_states 增加 quality_reason

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25

只有一列：看不清的具体原因（`too_blurry` / `too_dark` / `overexposed` / `no_subject`）。
NULL 表示这张图通过了质量门（或质量门当时是关闭的），与旧数据兼容。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shedding_states",
        sa.Column("quality_reason", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shedding_states", "quality_reason")

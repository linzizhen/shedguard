"""判定指纹：shedding_states 增加 pipeline_signature

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-27

为什么需要这一列：缓存命中条件原来只比 `state_version` 与 `classifier_name`，
但输入质量门的开关与三条阈值同样会改变判定结果。开着门把一张糊图判成
`unknown/too_blurry` 之后，如果有人把门关掉、再用同一张照片拍照（`ingest`
按 SHA-256 去重会复用同一个 `image_id`），旧结论就会被原样返回，App 继续
显示「这张有点糊」。把整套参数压成一个指纹存下来，指纹不同就重算。

NULL 表示这一行是加指纹之前写的，一律当作「不确定用的是什么参数」重算。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shedding_states",
        sa.Column("pipeline_signature", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shedding_states", "pipeline_signature")

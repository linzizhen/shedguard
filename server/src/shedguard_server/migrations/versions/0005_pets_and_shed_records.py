"""pets 与 shed_records 表。

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.create_table(
        "pets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("species", sa.String(64), nullable=False),
        sa.Column("morph", sa.String(64), nullable=True),
        sa.Column("birth_date", sa.String(10), nullable=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
    )
    op.create_table(
        "shed_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pet_id", sa.String(36), sa.ForeignKey("pets.id"), nullable=False),
        sa.Column("started_on", sa.String(10), nullable=False),
        sa.Column("completed_on", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.String(40), nullable=False),
        sa.Column("updated_at_utc", sa.String(40), nullable=False),
        sa.UniqueConstraint("pet_id", "started_on", name="uq_shed_records_pet_started"),
    )
    op.create_index("ix_shed_records_pet_id", "shed_records", ["pet_id"])


def downgrade() -> None:
    op.drop_index("ix_shed_records_pet_id", table_name="shed_records")
    op.drop_table("shed_records")
    op.drop_table("pets")

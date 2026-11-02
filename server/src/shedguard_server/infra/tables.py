"""表定义。字段与类型见规格第 4.1 节。"""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表的声明式基类。"""


class ImageRow(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rel_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    captured_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    local_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    received_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        Index("ix_images_date_device_captured", "local_date", "device_id", "captured_at_utc"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"ImageRow(id={self.id!r}, sha256={self.sha256[:8]!r})"


class ShedEventRow(Base):
    __tablename__ = "shed_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("device_id", "event_date", name="uq_shed_events_device_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"ShedEventRow(id={self.id!r}, date={self.event_date!r})"
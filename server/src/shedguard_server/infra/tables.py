"""表定义。字段与类型见规格第 4.1 节。"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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


class FrameMetricRow(Base):
    """一天一帧的体表信号。字段与类型见核心链路规格第 5.3 节。"""

    __tablename__ = "frame_metrics"

    image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("images.id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_date: Mapped[str] = mapped_column(String(10), nullable=False)
    detected: Mapped[int] = mapped_column(Integer, nullable=False)
    box_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector_name: Mapped[str] = mapped_column(String(64), nullable=False)
    detector_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized: Mapped[int] = mapped_column(Integer, nullable=False)
    exposure_scale: Mapped[float] = mapped_column(Float, nullable=False)
    lightness_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    lightness_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturation_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_light_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    color_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    background_lightness: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    metrics_version: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_frame_metrics_device_date", "device_id", "local_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"FrameMetricRow(image_id={self.image_id!r}, date={self.local_date!r})"


class SheddingStateRow(Base):
    """一张图的蜕皮状态。字段与类型见蜕皮状态规格第 6 节。

    `device_id` 与 `local_date` 是从 `images` 冗余过来的，和 `frame_metrics`
    同一做法：按设备与日期区间聚合是主要查询，不必每次回连大表。
    """

    __tablename__ = "shedding_states"

    image_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("images.id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_date: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    probabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detector_name: Mapped[str] = mapped_column(String(64), nullable=False)
    classifier_name: Mapped[str] = mapped_column(String(64), nullable=False)
    box_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    state_version: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_shedding_states_device_date", "device_id", "local_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"SheddingStateRow(image_id={self.image_id!r}, state={self.state!r})"
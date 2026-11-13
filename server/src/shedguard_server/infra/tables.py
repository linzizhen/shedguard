"""表定义。字段与类型见规格第 4.1 节。"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表的声明式基类。"""


class UserRow(Base):
    """匿名账号；只存令牌的 sha256 摘要，不存明文。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    last_seen_at_utc: Mapped[str | None] = mapped_column(String(40), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"UserRow(id={self.id!r})"


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


class PetRow(Base):
    """App 端手动管理的宠物。"""

    __tablename__ = "pets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    species: Mapped[str] = mapped_column(String(64), nullable=False)
    morph: Mapped[str | None] = mapped_column(String(64), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"PetRow(id={self.id!r}, name={self.name!r})"


class ShedRecordRow(Base):
    """一次手动记录的蜕皮。同一宠物同一天只能开始一次蜕皮。"""

    __tablename__ = "shed_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pets.id"), nullable=False, index=True
    )
    started_on: Mapped[str] = mapped_column(String(10), nullable=False)
    completed_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("pet_id", "started_on", name="uq_shed_records_pet_started"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"ShedRecordRow(id={self.id!r}, pet={self.pet_id!r})"


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


class PushDeviceRow(Base):
    """App 上报的推送目标；token 唯一，同一台手机重复上报时覆盖。"""

    __tablename__ = "push_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pets.id"), nullable=True, index=True
    )
    expo_push_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"PushDeviceRow(id={self.id!r}, platform={self.platform!r})"


class AlertRow(Base):
    """一条蜕皮提醒。同一设备同一天同一类型只保留一条。"""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pets.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    local_date: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("images.id"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    delivered_at_utc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    read_at_utc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    push_status: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint("device_id", "local_date", "kind", name="ux_alerts_device_date_kind"),
        Index("ix_alerts_device_date", "device_id", "local_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"AlertRow(id={self.id!r}, kind={self.kind!r}, date={self.local_date!r})"


class PortraitSettingRow(Base):
    """一只宠物的萌照偏好；没这行时用代码默认值。"""

    __tablename__ = "portrait_settings"

    pet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pets.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    start_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    end_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"PortraitSettingRow(pet_id={self.pet_id!r}, per_day={self.per_day!r})"


class PortraitShotRow(Base):
    """一张已生成的萌照。同一设备同一天同一槽位只会生成一次。"""

    __tablename__ = "portrait_shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pets.id"), nullable=True, index=True
    )
    local_date: Mapped[str] = mapped_column(String(10), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    source_image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("images.id"), nullable=True
    )
    rel_path: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    dhash: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "device_id", "local_date", "slot", name="ux_portrait_shots_device_date_slot"
        ),
        Index("ix_portrait_shots_pet_date", "pet_id", "local_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return (
            f"PortraitShotRow(id={self.id!r}, date={self.local_date!r}, slot={self.slot!r})"
        )


class PortraitFeedbackRow(Base):
    """用户对萌照的反馈；`crop_head` 会额外带一个人工框。"""

    __tablename__ = "portrait_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    shot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portrait_shots.id"), nullable=False, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    crop_box: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("shot_id", "kind", name="ux_portrait_feedback_shot_kind"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"PortraitFeedbackRow(id={self.id!r}, kind={self.kind!r})"

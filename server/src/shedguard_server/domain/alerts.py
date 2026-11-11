"""提醒（alert）与推送目标（push device）的领域值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

#: 触发提醒的蜕皮状态。
SHEDDING_STATE = "shedding"

#: 目前唯一的提醒类型：检测到开始蜕皮。
ALERT_KIND_SHEDDING = "shedding_detected"

#: 推送状态取值。
PUSH_PENDING = "pending"
PUSH_SENT = "sent"
PUSH_FAILED = "failed"
PUSH_SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PushDevice:
    """一台设备的推送目标；`pet_id` 用于把提醒挂到宠物上。"""

    id: str
    device_id: str | None
    pet_id: str | None
    expo_push_token: str
    platform: str
    created_at_utc: datetime
    updated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class Alert:
    """一条提醒事件。`push_status` 记录投递结果，便于排查与重试。"""

    id: str
    device_id: str
    pet_id: str | None
    kind: str
    local_date: date
    state: str
    image_id: str | None
    confidence: float | None
    created_at_utc: datetime
    delivered_at_utc: datetime | None
    push_status: str
    read_at_utc: datetime | None = None

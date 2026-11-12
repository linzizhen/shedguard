"""设备健康的纯判定逻辑（不触碰数据库，便于单测）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from shedguard_server.domain.alerts import (
    ALERT_KIND_DEVICE_SILENT,
    ALERT_KIND_NO_DETECTION,
)

#: 默认静默阈值（小时）。
DEFAULT_SILENCE_HOURS = 6
#: 默认连续未检出次数阈值。
DEFAULT_NO_DETECTION_STREAK = 5


@dataclass(frozen=True, slots=True)
class DeviceHealthInput:
    """判定一台设备是否异常所需的全部输入。"""

    device_id: str
    now: datetime
    last_upload_at: datetime | None
    recent_detections: tuple[bool, ...]
    capture_start_hour: int
    capture_end_hour: int
    timezone: str


@dataclass(frozen=True, slots=True)
class HealthFinding:
    """一条设备异常结论。"""

    kind: str
    detail: str


def evaluate_device_health(
    data: DeviceHealthInput,
    *,
    silence_hours: int = DEFAULT_SILENCE_HOURS,
    no_detection_streak: int = DEFAULT_NO_DETECTION_STREAK,
) -> list[HealthFinding]:
    """返回该设备当前的健康异常列表；正常时返回空列表。"""
    findings: list[HealthFinding] = []
    local_now = data.now.astimezone(ZoneInfo(data.timezone))

    active = _in_active_window(
        local_now, data.capture_start_hour, data.capture_end_hour
    )
    if (
        active
        and data.last_upload_at is not None
        and data.now - data.last_upload_at > timedelta(hours=silence_hours)
    ):
        hours = int((data.now - data.last_upload_at).total_seconds() // 3600)
        findings.append(
            HealthFinding(
                kind=ALERT_KIND_DEVICE_SILENT,
                detail=f"已经 {hours} 小时没收到照片，请检查电源与网络。",
            )
        )

    if len(data.recent_detections) >= no_detection_streak:
        recent = data.recent_detections[:no_detection_streak]
        if not any(recent):
            findings.append(
                HealthFinding(
                    kind=ALERT_KIND_NO_DETECTION,
                    detail=f"连续 {no_detection_streak} 张照片没拍到守宫，请调整机位。",
                )
            )

    return findings


def _in_active_window(local_now: datetime, start_hour: int, end_hour: int) -> bool:
    """活跃时段为 [start_hour, end_hour)；支持跨午夜。"""
    hour = local_now.hour
    if start_hour <= end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour

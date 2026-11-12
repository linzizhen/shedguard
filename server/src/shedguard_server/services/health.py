"""设备健康兜底扫描：把「沉默」变成显式提醒。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.health import DeviceHealthInput, evaluate_device_health
from shedguard_server.domain.push import PushGateway
from shedguard_server.infra.repository import (
    AlertRepository,
    ImageRepository,
    PushDeviceRepository,
    SheddingStateRepository,
)
from shedguard_server.services.alerts import AlertService

logger = logging.getLogger("shedguard.health")


def scan_once(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    gateway: PushGateway,
    now: datetime | None = None,
) -> int:
    """扫描所有已知设备，返回本次新建的提醒条数。"""
    moment = now or datetime.now(UTC)
    local_date = moment.astimezone(ZoneInfo(settings.timezone)).date()
    created = 0
    with session_factory() as session:
        alerts = AlertRepository(session)
        devices = PushDeviceRepository(session)
        images = ImageRepository(session)
        states = SheddingStateRepository(session)
        service = AlertService(
            alerts, devices, gateway, cooldown_hours=settings.alert_cooldown_hours
        )
        for device_id in devices.list_device_ids():
            data = DeviceHealthInput(
                device_id=device_id,
                now=moment,
                last_upload_at=images.latest_captured_at(device_id),
                recent_detections=states.recent_detections(
                    device_id, settings.no_detection_streak
                ),
                capture_start_hour=settings.capture_start_hour,
                capture_end_hour=settings.capture_end_hour,
                timezone=settings.timezone,
            )
            findings = evaluate_device_health(
                data,
                silence_hours=settings.device_silence_hours,
                no_detection_streak=settings.no_detection_streak,
            )
            for finding in findings:
                alert = service.create_alert(
                    device_id=device_id,
                    local_date=local_date,
                    kind=finding.kind,
                    pet_id=devices.pet_for_device(device_id),
                    now=moment,
                )
                if alert is None:
                    continue
                service.deliver(alert, now=moment)
                created += 1
                logger.info(
                    "设备健康提醒 device_id=%s kind=%s", device_id, finding.kind
                )
    return created

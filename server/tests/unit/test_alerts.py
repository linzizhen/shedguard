"""AlertService 的单元测试：用内存替身代替仓储与推送网关。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import cast

from shedguard_server.domain.alerts import (
    ALERT_KIND_SHEDDING,
    PUSH_FAILED,
    PUSH_SENT,
    PUSH_SKIPPED,
    Alert,
    PushDevice,
)
from shedguard_server.domain.push import PushMessage, PushOutcome, PushStatus
from shedguard_server.infra.repository import AlertRepository, PushDeviceRepository
from shedguard_server.services.alerts import AlertService

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


class FakeAlertRepository:
    def __init__(self) -> None:
        self.rows: dict[str, Alert] = {}

    def find(self, device_id: str, local_date: date, kind: str) -> Alert | None:
        for row in self.rows.values():
            if (row.device_id, row.local_date, row.kind) == (device_id, local_date, kind):
                return row
        return None

    def get(self, alert_id: str) -> Alert | None:
        return self.rows.get(alert_id)

    def add(self, alert: Alert) -> None:
        self.rows[alert.id] = alert

    def update(self, alert: Alert) -> None:
        self.rows[alert.id] = alert

    def list(
        self, *, device_id: str | None = None, pet_id: str | None = None, limit: int = 50
    ) -> list[Alert]:
        return list(self.rows.values())[:limit]

    def find_recent_delivered(
        self, device_id: str, kind: str, *, since: datetime
    ) -> Alert | None:
        for row in self.rows.values():
            if (
                row.device_id == device_id
                and row.kind == kind
                and row.push_status == PUSH_SENT
                and row.delivered_at_utc is not None
                and row.delivered_at_utc >= since
            ):
                return row
        return None


class FakeDeviceRepository:
    def __init__(self, devices: list[PushDevice] | None = None) -> None:
        self.devices = devices or []
        self.deleted: list[str] = []

    def list_for(self, *, device_id: str | None, pet_id: str | None) -> list[PushDevice]:
        result = []
        for device in self.devices:
            if (device_id is not None and device.device_id == device_id) or (
                pet_id is not None and device.pet_id == pet_id
            ):
                result.append(device)
        return result

    def pet_for_device(self, device_id: str) -> str | None:
        for device in self.devices:
            if device.device_id == device_id and device.pet_id is not None:
                return device.pet_id
        return None

    def delete(self, device_pk: str) -> bool:
        self.deleted.append(device_pk)
        self.devices = [d for d in self.devices if d.id != device_pk]
        return True


class FakeGateway:
    def __init__(self, status: PushStatus = PushStatus.SENT) -> None:
        self.status = status
        self.sent: list[PushMessage] = []

    def send(self, message: PushMessage) -> PushOutcome:
        self.sent.append(message)
        return PushOutcome(status=self.status)


def make_device(pid: str = "d1", token: str = "tok", pet_id: str | None = "pet1") -> PushDevice:
    return PushDevice(
        id=pid,
        device_id="device-1",
        pet_id=pet_id,
        expo_push_token=token,
        platform="ios",
        created_at_utc=NOW,
        updated_at_utc=NOW,
    )


def make_service(
    alerts: FakeAlertRepository | None = None,
    devices: FakeDeviceRepository | None = None,
    gateway: FakeGateway | None = None,
    *,
    cooldown_hours: int = 24,
) -> AlertService:
    return AlertService(
        cast(AlertRepository, alerts or FakeAlertRepository()),
        cast(PushDeviceRepository, devices or FakeDeviceRepository()),
        gateway or FakeGateway(),
        cooldown_hours=cooldown_hours,
    )


class TestCreateForTransition:
    def test_ignores_non_shedding_state(self) -> None:
        service = make_service()
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="normal",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is None

    def test_creates_alert_for_shedding(self) -> None:
        alerts = FakeAlertRepository()
        service = make_service(alerts=alerts)
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            pet_id="pet1",
            now=NOW,
        )
        assert alert is not None
        assert alert.kind == ALERT_KIND_SHEDDING
        assert alert.push_status == "pending"
        assert alerts.find("device-1", date(2026, 11, 11), ALERT_KIND_SHEDDING) is not None

    def test_deduplicates_same_day(self) -> None:
        service = make_service()
        first = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        second = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img2",
            confidence=0.8,
            now=NOW,
        )
        assert first is not None
        assert second is None


class TestDeliver:
    def test_skips_when_no_targets(self) -> None:
        alerts = FakeAlertRepository()
        service = make_service(alerts=alerts)
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_SKIPPED
        assert delivered.delivered_at_utc is None

    def test_skips_targets_without_token(self) -> None:
        # 只绑定设备、没开系统通知（空 token）：不推送，也不记为失败。
        devices = FakeDeviceRepository([make_device(token="")])
        gateway = FakeGateway(PushStatus.SENT)
        service = make_service(devices=devices, gateway=gateway)
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_SKIPPED
        assert gateway.sent == []

    def test_sends_to_registered_device(self) -> None:
        devices = FakeDeviceRepository([make_device()])
        gateway = FakeGateway(PushStatus.SENT)
        service = make_service(devices=devices, gateway=gateway)
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            pet_id="pet1",
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_SENT
        assert delivered.delivered_at_utc == NOW
        assert gateway.sent[0].to == "tok"
        assert gateway.sent[0].data["alert_id"] == alert.id

    def test_removes_invalid_token(self) -> None:
        devices = FakeDeviceRepository([make_device()])
        gateway = FakeGateway(PushStatus.INVALID)
        service = make_service(devices=devices, gateway=gateway)
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_FAILED
        assert devices.deleted == ["d1"]

    def test_marks_failed_on_gateway_error(self) -> None:
        devices = FakeDeviceRepository([make_device()])
        service = make_service(devices=devices, gateway=FakeGateway(PushStatus.FAILED))
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_FAILED
        assert delivered.delivered_at_utc is None

    def test_skips_when_gateway_disabled(self) -> None:
        devices = FakeDeviceRepository([make_device()])
        service = make_service(devices=devices, gateway=FakeGateway(PushStatus.SKIPPED))
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            pet_id="pet1",
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_SKIPPED
        assert delivered.delivered_at_utc is None

    def test_cooldown_skips_recent_delivery(self) -> None:
        devices = FakeDeviceRepository([make_device()])
        gateway = FakeGateway(PushStatus.SENT)
        alerts = FakeAlertRepository()
        service = make_service(alerts=alerts, devices=devices, gateway=gateway)
        # 先造一条已投递的提醒。
        alerts.rows["old"] = Alert(
            id="old",
            device_id="device-1",
            pet_id="pet1",
            kind=ALERT_KIND_SHEDDING,
            local_date=date(2026, 11, 10),
            state="shedding",
            image_id="img0",
            confidence=0.9,
            created_at_utc=NOW - timedelta(hours=2),
            delivered_at_utc=NOW - timedelta(hours=1),
            push_status=PUSH_SENT,
        )
        alert = service.create_for_transition(
            device_id="device-1",
            local_date=date(2026, 11, 11),
            state="shedding",
            image_id="img1",
            confidence=0.9,
            now=NOW,
        )
        assert alert is not None
        delivered = service.deliver(alert, now=NOW)
        assert delivered.push_status == PUSH_SKIPPED
        assert gateway.sent == []

"""提醒创建与推送投递。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from shedguard_server.domain.alerts import (
    ALERT_KIND_DEVICE_SILENT,
    ALERT_KIND_NO_DETECTION,
    ALERT_KIND_SHEDDING,
    PUSH_FAILED,
    PUSH_PENDING,
    PUSH_SENT,
    PUSH_SKIPPED,
    SHEDDING_STATE,
    Alert,
)
from shedguard_server.domain.push import PushGateway, PushMessage, PushStatus
from shedguard_server.infra.repository import AlertRepository, PushDeviceRepository

DEFAULT_COOLDOWN_HOURS = 24

ALERT_TITLE = "守宫正在蜕皮"
ALERT_BODY = "检测到蜕皮白皮，请打开照片查看。"

#: 每类提醒的推送标题与正文（正文可按 detail 覆盖）。
MESSAGES: dict[str, tuple[str, str]] = {
    ALERT_KIND_SHEDDING: (ALERT_TITLE, ALERT_BODY),
    ALERT_KIND_DEVICE_SILENT: ("设备可能离线", "已经很久没收到照片，请检查电源与网络。"),
    ALERT_KIND_NO_DETECTION: ("看不到守宫", "连续多张照片没拍到守宫，请调整机位。"),
}


class AlertService:
    """在状态跃迁到「蜕皮中」时创建提醒，并把提醒推送到已注册设备。"""

    def __init__(
        self,
        alerts: AlertRepository,
        devices: PushDeviceRepository,
        gateway: PushGateway,
        *,
        cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
    ) -> None:
        self._alerts = alerts
        self._devices = devices
        self._gateway = gateway
        self._cooldown_hours = cooldown_hours

    def create_alert(
        self,
        *,
        device_id: str,
        local_date: date,
        kind: str,
        state: str = "",
        image_id: str | None = None,
        confidence: float | None = None,
        pet_id: str | None = None,
        now: datetime | None = None,
    ) -> Alert | None:
        """按 (device_id, local_date, kind) 去重后创建一条提醒。"""
        if self._alerts.find(device_id, local_date, kind) is not None:
            return None
        created_at = now or datetime.now(UTC)
        alert = Alert(
            id=str(uuid4()),
            device_id=device_id,
            pet_id=pet_id,
            kind=kind,
            local_date=local_date,
            state=state,
            image_id=image_id,
            confidence=confidence,
            created_at_utc=created_at,
            delivered_at_utc=None,
            push_status=PUSH_PENDING,
        )
        self._alerts.add(alert)
        return alert

    def create_for_transition(
        self,
        *,
        device_id: str,
        local_date: date,
        state: str,
        image_id: str | None,
        confidence: float | None,
        pet_id: str | None = None,
        now: datetime | None = None,
    ) -> Alert | None:
        """仅当状态是「蜕皮中」且当天尚无同类提醒时创建；否则返回 None。"""
        if state != SHEDDING_STATE:
            return None
        return self.create_alert(
            device_id=device_id,
            local_date=local_date,
            kind=ALERT_KIND_SHEDDING,
            state=state,
            image_id=image_id,
            confidence=confidence,
            pet_id=pet_id,
            now=now,
        )

    def deliver(self, alert: Alert, *, now: datetime | None = None) -> Alert:
        """把提醒推给该设备/宠物绑定的所有推送目标，并回写投递状态。"""
        moment = now or datetime.now(UTC)

        if self._cooling_down(alert, moment):
            return self._mark(alert, PUSH_SKIPPED, delivered_at=None)

        targets = self._devices.list_for(
            device_id=alert.device_id, pet_id=alert.pet_id
        )
        if not targets:
            return self._mark(alert, PUSH_SKIPPED, delivered_at=None)

        message_data = self._message_data(alert)
        title, body = MESSAGES.get(alert.kind, (ALERT_TITLE, ALERT_BODY))
        any_sent = False
        any_attempt_failed = False
        for target in targets:
            if not target.expo_push_token:
                # 只绑定设备、没开启系统通知（Expo Go / 未打包）时跳过推送。
                continue
            message = PushMessage(
                to=target.expo_push_token,
                title=title,
                body=body,
                data=message_data,
            )
            outcome = self._gateway.send(message)
            if outcome.status is PushStatus.SENT:
                any_sent = True
            elif outcome.status is PushStatus.INVALID:
                # token 已失效：清理掉，避免后续反复尝试。
                self._devices.delete(target.id)
                any_attempt_failed = True
            elif outcome.status is PushStatus.SKIPPED:
                # 推送被禁用（SkippedPushGateway）：不算失败，提醒仍可在 App 列表查看。
                continue
            else:
                any_attempt_failed = True

        if any_sent:
            return self._mark(alert, PUSH_SENT, delivered_at=moment)
        if any_attempt_failed:
            return self._mark(alert, PUSH_FAILED, delivered_at=None)
        return self._mark(alert, PUSH_SKIPPED, delivered_at=None)

    def _cooling_down(self, alert: Alert, moment: datetime) -> bool:
        if self._cooldown_hours <= 0:
            return False
        since = moment - timedelta(hours=self._cooldown_hours)
        recent = self._alerts.find_recent_delivered(alert.device_id, alert.kind, since=since)
        return recent is not None

    def _mark(
        self, alert: Alert, status: str, *, delivered_at: datetime | None
    ) -> Alert:
        updated = Alert(
            id=alert.id,
            device_id=alert.device_id,
            pet_id=alert.pet_id,
            kind=alert.kind,
            local_date=alert.local_date,
            state=alert.state,
            image_id=alert.image_id,
            confidence=alert.confidence,
            created_at_utc=alert.created_at_utc,
            delivered_at_utc=delivered_at,
            push_status=status,
            read_at_utc=alert.read_at_utc,
        )
        self._alerts.update(updated)
        return updated

    @staticmethod
    def _message_data(alert: Alert) -> dict[str, str]:
        data = {
            "alert_id": alert.id,
            "kind": alert.kind,
            "local_date": alert.local_date.isoformat(),
        }
        if alert.pet_id is not None:
            data["pet_id"] = alert.pet_id
        return data

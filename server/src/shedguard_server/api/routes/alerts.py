"""蜕皮提醒查询与已读标记接口。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from shedguard_server.api.dependencies import get_alert_repository
from shedguard_server.domain.alerts import Alert
from shedguard_server.errors import NotFoundError
from shedguard_server.infra.repository import AlertRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertPatch(BaseModel):
    """标记提醒已读。"""

    read: bool = True


def serialize_alert(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "device_id": alert.device_id,
        "pet_id": alert.pet_id,
        "kind": alert.kind,
        "local_date": alert.local_date.isoformat(),
        "state": alert.state,
        "image_id": alert.image_id,
        "confidence": alert.confidence,
        "created_at_utc": alert.created_at_utc.isoformat(),
        "delivered_at_utc": (
            alert.delivered_at_utc.isoformat() if alert.delivered_at_utc else None
        ),
        "read_at_utc": alert.read_at_utc.isoformat() if alert.read_at_utc else None,
        "push_status": alert.push_status,
    }


@router.get("")
def list_alerts(
    repository: Annotated[AlertRepository, Depends(get_alert_repository)],
    device_id: Annotated[str | None, Query()] = None,
    pet_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    items = repository.list(device_id=device_id, pet_id=pet_id, limit=limit)
    return {"items": [serialize_alert(alert) for alert in items]}


@router.patch("/{alert_id}")
def patch_alert(
    alert_id: str,
    body: AlertPatch,
    repository: Annotated[AlertRepository, Depends(get_alert_repository)],
) -> dict[str, Any]:
    alert = repository.get(alert_id)
    if alert is None:
        raise NotFoundError(f"提醒不存在: {alert_id}")
    read_at = alert.read_at_utc
    if body.read and read_at is None:
        read_at = datetime.now(UTC)
    elif not body.read:
        read_at = None
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
        delivered_at_utc=alert.delivered_at_utc,
        push_status=alert.push_status,
        read_at_utc=read_at,
    )
    repository.update(updated)
    return serialize_alert(updated)

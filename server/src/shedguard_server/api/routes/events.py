"""蜕皮事件接口：记录（幂等覆盖）与按条件查询。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shedguard_server.api.dependencies import get_session
from shedguard_server.domain.models import ShedEvent
from shedguard_server.errors import InvalidRequestError
from shedguard_server.infra.repository import ShedEventRepository
from shedguard_server.services.events import ShedEventService

router = APIRouter(prefix="/api/v1/shed-events", tags=["shed-events"])


class ShedEventPayload(BaseModel):
    """PUT 请求体：outcome 必填，notes 可空。"""

    outcome: str
    notes: str | None = None


def get_event_repository(session: Annotated[Session, Depends(get_session)]) -> ShedEventRepository:
    return ShedEventRepository(session)


def get_event_service(
    repository: Annotated[ShedEventRepository, Depends(get_event_repository)],
) -> ShedEventService:
    return ShedEventService(repository)


def _serialize(event: ShedEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "device_id": event.device_id,
        "event_date": event.event_date.isoformat(),
        "outcome": event.outcome,
        "notes": event.notes,
        "created_at_utc": event.created_at_utc.isoformat().replace("+00:00", "Z"),
        "updated_at_utc": event.updated_at_utc.isoformat().replace("+00:00", "Z"),
    }


def _parse_optional_day(raw: str | None, name: str) -> date | None:
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}") from exc
    if parsed.isoformat() != raw:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}")
    return parsed


@router.put("/{device_id}/{event_date}")
def put_shed_event(
    device_id: str,
    event_date: str,
    payload: ShedEventPayload,
    service: Annotated[ShedEventService, Depends(get_event_service)],
) -> JSONResponse:
    event, created = service.record(
        device_id_raw=device_id,
        event_date_raw=event_date,
        outcome_raw=payload.outcome,
        notes_raw=payload.notes,
    )
    return JSONResponse(_serialize(event), status_code=201 if created else 200)


@router.get("")
def list_shed_events(
    service: Annotated[ShedEventService, Depends(get_event_service)],
    device_id: Annotated[str | None, Query()] = None,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    events = service.list_events(
        device_id_raw=device_id,
        start=_parse_optional_day(from_date, "from"),
        end=_parse_optional_day(to_date, "to"),
    )
    return {"items": [_serialize(event) for event in events], "total": len(events)}
"""蜕皮事件编排：校验输入、生成 id、处理同日覆盖。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from shedguard_server.domain.events import parse_event_date, validate_notes, validate_outcome
from shedguard_server.domain.models import ShedEvent
from shedguard_server.domain.validation import validate_device_id
from shedguard_server.infra.repository import ShedEventRepository


class ShedEventService:
    """记录与查询蜕皮事件。"""

    def __init__(self, repository: ShedEventRepository) -> None:
        self._repository = repository

    def record(
        self,
        *,
        device_id_raw: str | None,
        event_date_raw: str,
        outcome_raw: str,
        notes_raw: str | None,
        now: datetime | None = None,
    ) -> tuple[ShedEvent, bool]:
        """写入事件；返回 (事件, 是否新建)。同日同设备覆盖已有记录。"""
        device_id = validate_device_id(device_id_raw)
        event_date = parse_event_date(event_date_raw)
        outcome = validate_outcome(outcome_raw)
        notes = validate_notes(notes_raw)
        moment = now or datetime.now(UTC)

        existing = self._repository.find(device_id, event_date)
        if existing is None:
            created = ShedEvent(
                id=str(uuid4()),
                device_id=device_id,
                event_date=event_date,
                outcome=outcome,
                notes=notes,
                created_at_utc=moment,
                updated_at_utc=moment,
            )
            return self._repository.save(created)

        updated = ShedEvent(
            id=existing.id,
            device_id=device_id,
            event_date=event_date,
            outcome=outcome,
            notes=notes,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=moment,
        )
        return self._repository.save(updated)

    def list_events(
        self,
        *,
        device_id_raw: str | None,
        start: date | None,
        end: date | None,
    ) -> list[ShedEvent]:
        device_id = validate_device_id(device_id_raw) if device_id_raw else None
        return self._repository.list_events(device_id=device_id, start=start, end=end)
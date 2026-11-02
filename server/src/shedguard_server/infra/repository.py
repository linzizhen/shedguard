"""持久化：把领域值对象与 images 表互相转换。"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from shedguard_server.domain.models import ImageRecord, ShedEvent
from shedguard_server.infra.tables import ImageRow, ShedEventRow


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _to_record(row: ImageRow) -> ImageRecord:
    return ImageRecord(
        id=row.id,
        device_id=row.device_id,
        rel_path=row.rel_path,
        byte_size=row.byte_size,
        sha256=row.sha256,
        captured_at_utc=_parse_utc(row.captured_at_utc),
        local_date=date.fromisoformat(row.local_date),
        received_at_utc=_parse_utc(row.received_at_utc),
    )


def _to_row(record: ImageRecord) -> ImageRow:
    return ImageRow(
        id=record.id,
        device_id=record.device_id,
        rel_path=record.rel_path,
        byte_size=record.byte_size,
        sha256=record.sha256,
        captured_at_utc=record.captured_at_utc.isoformat(),
        local_date=record.local_date.isoformat(),
        received_at_utc=record.received_at_utc.isoformat(),
    )


class ImageRepository:
    """images 表的读写；所有语句参数化。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_sha256(self, sha256: str) -> ImageRecord | None:
        row = self._session.scalar(select(ImageRow).where(ImageRow.sha256 == sha256))
        return _to_record(row) if row is not None else None

    def find_by_id(self, image_id: str) -> ImageRecord | None:
        row = self._session.get(ImageRow, image_id)
        return _to_record(row) if row is not None else None

    def add(self, record: ImageRecord) -> None:
        self._session.add(_to_row(record))
        self._session.commit()

    def list_for_date(
        self,
        local_date: str,
        *,
        device_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ImageRecord], int]:
        conditions = [ImageRow.local_date == local_date]
        if device_id is not None:
            conditions.append(ImageRow.device_id == device_id)

        total = self._session.scalar(
            select(func.count()).select_from(ImageRow).where(*conditions)
        ) or 0
        rows = self._session.scalars(
            select(ImageRow)
            .where(*conditions)
            .order_by(ImageRow.captured_at_utc, ImageRow.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_record(row) for row in rows], int(total)

    def list_for_range(self, device_id: str, start: date, end: date) -> list[ImageRecord]:
        """取某设备在本地日期区间内的全部图片，按拍摄时间升序。"""
        rows = self._session.scalars(
            select(ImageRow)
            .where(
                ImageRow.device_id == device_id,
                ImageRow.local_date >= start.isoformat(),
                ImageRow.local_date <= end.isoformat(),
            )
            .order_by(ImageRow.captured_at_utc, ImageRow.id)
        ).all()
        return [_to_record(row) for row in rows]


def _to_event(row: ShedEventRow) -> ShedEvent:
    return ShedEvent(
        id=row.id,
        device_id=row.device_id,
        event_date=date.fromisoformat(row.event_date),
        outcome=row.outcome,
        notes=row.notes,
        created_at_utc=_parse_utc(row.created_at_utc),
        updated_at_utc=_parse_utc(row.updated_at_utc),
    )


def _to_event_row(event: ShedEvent) -> ShedEventRow:
    return ShedEventRow(
        id=event.id,
        device_id=event.device_id,
        event_date=event.event_date.isoformat(),
        outcome=event.outcome,
        notes=event.notes,
        created_at_utc=event.created_at_utc.isoformat(),
        updated_at_utc=event.updated_at_utc.isoformat(),
    )


class ShedEventRepository:
    """shed_events 表的读写；同一设备同一天只保留一条。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, device_id: str, event_date: date) -> ShedEvent | None:
        row = self._session.scalar(
            select(ShedEventRow).where(
                ShedEventRow.device_id == device_id,
                ShedEventRow.event_date == event_date.isoformat(),
            )
        )
        return _to_event(row) if row is not None else None

    def save(self, event: ShedEvent) -> tuple[ShedEvent, bool]:
        """写入或覆盖；返回值第二项表示是否新建。"""
        existing = self._session.scalar(
            select(ShedEventRow).where(
                ShedEventRow.device_id == event.device_id,
                ShedEventRow.event_date == event.event_date.isoformat(),
            )
        )
        if existing is None:
            self._session.add(_to_event_row(event))
            self._session.commit()
            return event, True

        existing.outcome = event.outcome
        existing.notes = event.notes
        existing.updated_at_utc = event.updated_at_utc.isoformat()
        self._session.commit()
        self._session.refresh(existing)
        return _to_event(existing), False

    def list_events(
        self,
        *,
        device_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShedEvent]:
        conditions: list[ColumnElement[bool]] = []
        if device_id is not None:
            conditions.append(ShedEventRow.device_id == device_id)
        if start is not None:
            conditions.append(ShedEventRow.event_date >= start.isoformat())
        if end is not None:
            conditions.append(ShedEventRow.event_date <= end.isoformat())

        rows = self._session.scalars(
            select(ShedEventRow)
            .where(*conditions)
            .order_by(ShedEventRow.event_date.desc(), ShedEventRow.id)
        ).all()
        return [_to_event(row) for row in rows]
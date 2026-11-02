"""持久化：把领域值对象与 images 表互相转换。"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shedguard_server.domain.models import ImageRecord
from shedguard_server.infra.tables import ImageRow


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
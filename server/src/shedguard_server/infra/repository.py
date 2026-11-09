"""持久化：把领域值对象与数据表互相转换。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from shedguard_server.domain.models import (
    FrameMetric,
    ImageRecord,
    SheddingState,
    ShedEvent,
)
from shedguard_server.domain.pets import Pet, ShedRecord
from shedguard_server.infra.tables import (
    FrameMetricRow,
    ImageRow,
    PetRow,
    SheddingStateRow,
    ShedEventRow,
    ShedRecordRow,
)


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


def _to_metric(row: FrameMetricRow) -> FrameMetric:
    box: tuple[int, int, int, int] | None = None
    if row.box_json is not None:
        raw = json.loads(row.box_json)
        box = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    return FrameMetric(
        image_id=row.image_id,
        device_id=row.device_id,
        local_date=date.fromisoformat(row.local_date),
        detected=bool(row.detected),
        box=box,
        detector_name=row.detector_name,
        detector_confidence=row.detector_confidence,
        normalized=bool(row.normalized),
        exposure_scale=row.exposure_scale,
        lightness_mean=row.lightness_mean,
        lightness_std=row.lightness_std,
        saturation_mean=row.saturation_mean,
        high_light_ratio=row.high_light_ratio,
        edge_density=row.edge_density,
        color_entropy=row.color_entropy,
        background_lightness=row.background_lightness,
        computed_at_utc=_parse_utc(row.computed_at_utc),
        metrics_version=row.metrics_version,
    )


def _to_metric_row(metric: FrameMetric) -> FrameMetricRow:
    return FrameMetricRow(
        image_id=metric.image_id,
        device_id=metric.device_id,
        local_date=metric.local_date.isoformat(),
        detected=int(metric.detected),
        box_json=json.dumps(list(metric.box)) if metric.box is not None else None,
        detector_name=metric.detector_name,
        detector_confidence=metric.detector_confidence,
        normalized=int(metric.normalized),
        exposure_scale=metric.exposure_scale,
        lightness_mean=metric.lightness_mean,
        lightness_std=metric.lightness_std,
        saturation_mean=metric.saturation_mean,
        high_light_ratio=metric.high_light_ratio,
        edge_density=metric.edge_density,
        color_entropy=metric.color_entropy,
        background_lightness=metric.background_lightness,
        computed_at_utc=metric.computed_at_utc.isoformat(),
        metrics_version=metric.metrics_version,
    )


class FrameMetricRepository:
    """frame_metrics 表的读写；一张图一行。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, image_id: str) -> FrameMetric | None:
        row = self._session.get(FrameMetricRow, image_id)
        return _to_metric(row) if row is not None else None

    def save(self, metric: FrameMetric) -> None:
        """写入或覆盖同一张图的指标。"""
        self._session.merge(_to_metric_row(metric))
        self._session.commit()

    def list_for_device(
        self, device_id: str, start: date, end: date
    ) -> list[FrameMetric]:
        rows = self._session.scalars(
            select(FrameMetricRow)
            .where(
                FrameMetricRow.device_id == device_id,
                FrameMetricRow.local_date >= start.isoformat(),
                FrameMetricRow.local_date <= end.isoformat(),
            )
            .order_by(FrameMetricRow.local_date)
        ).all()
        return [_to_metric(row) for row in rows]

    def recent_background(
        self, device_id: str, *, before: date, days: int
    ) -> list[float]:
        """取该设备在 before 之前若干天的背景亮度，用于估算曝光系数。"""
        window_start = before - timedelta(days=days)
        rows = self._session.scalars(
            select(FrameMetricRow)
            .where(
                FrameMetricRow.device_id == device_id,
                FrameMetricRow.local_date >= window_start.isoformat(),
                FrameMetricRow.local_date < before.isoformat(),
                FrameMetricRow.background_lightness.is_not(None),
            )
            .order_by(FrameMetricRow.local_date)
        ).all()
        return [value for row in rows if (value := row.background_lightness) is not None]


def _to_shedding_state(row: SheddingStateRow) -> SheddingState:
    box: tuple[int, int, int, int] | None = None
    if row.box_json is not None:
        raw_box = json.loads(row.box_json)
        box = (int(raw_box[0]), int(raw_box[1]), int(raw_box[2]), int(raw_box[3]))

    probabilities: dict[str, float] | None = None
    if row.probabilities_json is not None:
        raw_probabilities = json.loads(row.probabilities_json)
        probabilities = {str(name): float(value) for name, value in raw_probabilities.items()}

    return SheddingState(
        image_id=row.image_id,
        device_id=row.device_id,
        local_date=date.fromisoformat(row.local_date),
        state=row.state,
        confidence=row.confidence,
        probabilities=probabilities,
        detector_name=row.detector_name,
        classifier_name=row.classifier_name,
        box=box,
        computed_at_utc=_parse_utc(row.computed_at_utc),
        state_version=row.state_version,
    )


def _to_shedding_state_row(state: SheddingState) -> SheddingStateRow:
    return SheddingStateRow(
        image_id=state.image_id,
        device_id=state.device_id,
        local_date=state.local_date.isoformat(),
        state=state.state,
        confidence=state.confidence,
        probabilities_json=(
            json.dumps(state.probabilities, ensure_ascii=False)
            if state.probabilities is not None
            else None
        ),
        detector_name=state.detector_name,
        classifier_name=state.classifier_name,
        box_json=json.dumps(list(state.box)) if state.box is not None else None,
        computed_at_utc=state.computed_at_utc.isoformat(),
        state_version=state.state_version,
    )


class SheddingStateRepository:
    """shedding_states 表的读写；一张图一行。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, image_id: str) -> SheddingState | None:
        row = self._session.get(SheddingStateRow, image_id)
        return _to_shedding_state(row) if row is not None else None

    def save(self, state: SheddingState) -> None:
        """写入或覆盖同一张图的状态。"""
        self._session.merge(_to_shedding_state_row(state))
        self._session.commit()

    def list_for_device(
        self, device_id: str, start: date, end: date
    ) -> list[SheddingState]:
        rows = self._session.scalars(
            select(SheddingStateRow)
            .where(
                SheddingStateRow.device_id == device_id,
                SheddingStateRow.local_date >= start.isoformat(),
                SheddingStateRow.local_date <= end.isoformat(),
            )
            .order_by(SheddingStateRow.local_date, SheddingStateRow.image_id)
        ).all()
        return [_to_shedding_state(row) for row in rows]


def _to_pet(row: PetRow) -> Pet:
    return Pet(
        id=row.id,
        name=row.name,
        species=row.species,
        morph=row.morph,
        birth_date=date.fromisoformat(row.birth_date) if row.birth_date else None,
        created_at_utc=_parse_utc(row.created_at_utc),
        updated_at_utc=_parse_utc(row.updated_at_utc),
    )


def _to_pet_row(pet: Pet) -> PetRow:
    return PetRow(
        id=pet.id,
        name=pet.name,
        species=pet.species,
        morph=pet.morph,
        birth_date=pet.birth_date.isoformat() if pet.birth_date else None,
        created_at_utc=pet.created_at_utc.isoformat(),
        updated_at_utc=pet.updated_at_utc.isoformat(),
    )


class PetRepository:
    """pets 表的读写。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, pet_id: str) -> Pet | None:
        row = self._session.get(PetRow, pet_id)
        return _to_pet(row) if row is not None else None

    def list(self) -> list[Pet]:
        rows = self._session.scalars(select(PetRow).order_by(PetRow.created_at_utc)).all()
        return [_to_pet(row) for row in rows]

    def add(self, pet: Pet) -> None:
        self._session.add(_to_pet_row(pet))
        self._session.commit()

    def update(self, pet: Pet) -> None:
        self._session.merge(_to_pet_row(pet))
        self._session.commit()

    def delete(self, pet_id: str) -> bool:
        row = self._session.get(PetRow, pet_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


def _to_shed_record(row: ShedRecordRow) -> ShedRecord:
    return ShedRecord(
        id=row.id,
        pet_id=row.pet_id,
        started_on=date.fromisoformat(row.started_on),
        completed_on=date.fromisoformat(row.completed_on) if row.completed_on else None,
        notes=row.notes,
        created_at_utc=_parse_utc(row.created_at_utc),
        updated_at_utc=_parse_utc(row.updated_at_utc),
    )


def _to_shed_record_row(record: ShedRecord) -> ShedRecordRow:
    return ShedRecordRow(
        id=record.id,
        pet_id=record.pet_id,
        started_on=record.started_on.isoformat(),
        completed_on=record.completed_on.isoformat() if record.completed_on else None,
        notes=record.notes,
        created_at_utc=record.created_at_utc.isoformat(),
        updated_at_utc=record.updated_at_utc.isoformat(),
    )


class ShedRecordRepository:
    """shed_records 表的读写；同一宠物一天只能有一条记录。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, record_id: str) -> ShedRecord | None:
        row = self._session.get(ShedRecordRow, record_id)
        return _to_shed_record(row) if row is not None else None

    def find_by_started_on(self, pet_id: str, started_on: date) -> ShedRecord | None:
        row = self._session.scalar(
            select(ShedRecordRow).where(
                ShedRecordRow.pet_id == pet_id,
                ShedRecordRow.started_on == started_on.isoformat(),
            )
        )
        return _to_shed_record(row) if row is not None else None

    def add(self, record: ShedRecord) -> None:
        self._session.add(_to_shed_record_row(record))
        self._session.commit()

    def update(self, record: ShedRecord) -> None:
        self._session.merge(_to_shed_record_row(record))
        self._session.commit()

    def delete(self, record_id: str) -> bool:
        row = self._session.get(ShedRecordRow, record_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    def list_for_pet(self, pet_id: str) -> list[ShedRecord]:
        rows = self._session.scalars(
            select(ShedRecordRow)
            .where(ShedRecordRow.pet_id == pet_id)
            .order_by(ShedRecordRow.started_on.desc())
        ).all()
        return [_to_shed_record(row) for row in rows]

    def delete_for_pet(self, pet_id: str) -> None:
        """删除宠物时级联清掉它的蜕皮记录。"""
        rows = self._session.scalars(
            select(ShedRecordRow).where(ShedRecordRow.pet_id == pet_id)
        ).all()
        for row in rows:
            self._session.delete(row)
        self._session.commit()
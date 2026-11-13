"""持久化：把领域值对象与数据表互相转换。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from shedguard_server.domain.alerts import Alert, PushDevice
from shedguard_server.domain.models import (
    FrameMetric,
    ImageRecord,
    SheddingState,
    ShedEvent,
)
from shedguard_server.domain.pets import Pet, ShedRecord
from shedguard_server.domain.portrait import (
    PortraitFeedback,
    PortraitSetting,
    PortraitShot,
)
from shedguard_server.domain.user import User
from shedguard_server.infra.tables import (
    AlertRow,
    FrameMetricRow,
    ImageRow,
    PetRow,
    PortraitFeedbackRow,
    PortraitSettingRow,
    PortraitShotRow,
    PushDeviceRow,
    SheddingStateRow,
    ShedEventRow,
    ShedRecordRow,
    UserRow,
)

#: 迁移前历史宠物的归属占位账号；新数据一律写真实 owner_id。
LEGACY_OWNER_ID = "legacy"


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

    def latest_captured_at(self, device_id: str) -> datetime | None:
        """该设备最近一张图的拍摄时间；没有则返回 None。"""
        raw = self._session.scalar(
            select(func.max(ImageRow.captured_at_utc)).where(
                ImageRow.device_id == device_id
            )
        )
        return _parse_utc(raw) if raw else None

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

    def list_captured_before(self, cutoff: datetime) -> list[ImageRecord]:
        """取拍摄时间严格早于 `cutoff` 的图片，按时间升序；供保留策略清理。"""
        moment = cutoff if cutoff.tzinfo is not None else cutoff.replace(tzinfo=UTC)
        rows = self._session.scalars(
            select(ImageRow)
            .where(ImageRow.captured_at_utc < moment.astimezone(UTC).isoformat())
            .order_by(ImageRow.captured_at_utc, ImageRow.id)
        ).all()
        return [_to_record(row) for row in rows]

    def delete(self, image_id: str) -> bool:
        """删除图片行并提交；调用方需先清理子行与磁盘文件。"""
        row = self._session.get(ImageRow, image_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


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

    def delete_for_image(self, image_id: str) -> None:
        """删除该图的指标行；提交时机由调用方决定（保留策略随后删图片行并提交）。"""
        row = self._session.get(FrameMetricRow, image_id)
        if row is not None:
            self._session.delete(row)


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

    def recent_detections(self, device_id: str, limit: int) -> tuple[bool, ...]:
        """最近若干次判定的「是否检出守宫」，新→旧；box 为空视为未检出。"""
        rows = self._session.scalars(
            select(SheddingStateRow)
            .where(SheddingStateRow.device_id == device_id)
            .order_by(SheddingStateRow.local_date.desc(), SheddingStateRow.image_id.desc())
            .limit(limit)
        ).all()
        return tuple(row.box_json is not None for row in rows)

    def delete_for_image(self, image_id: str) -> None:
        """删除该图的状态行；提交时机由调用方决定（保留策略随后删图片行并提交）。"""
        row = self._session.get(SheddingStateRow, image_id)
        if row is not None:
            self._session.delete(row)


def _to_pet(row: PetRow) -> Pet:
    return Pet(
        id=row.id,
        name=row.name,
        species=row.species,
        morph=row.morph,
        birth_date=date.fromisoformat(row.birth_date) if row.birth_date else None,
        created_at_utc=_parse_utc(row.created_at_utc),
        updated_at_utc=_parse_utc(row.updated_at_utc),
        owner_id=row.owner_id,
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
        owner_id=pet.owner_id or LEGACY_OWNER_ID,
    )


def _to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        created_at_utc=_parse_utc(row.created_at_utc),
        last_seen_at_utc=_parse_utc(row.last_seen_at_utc) if row.last_seen_at_utc else None,
    )


def _to_user_row(user: User) -> UserRow:
    return UserRow(
        id=user.id,
        token_hash="",
        created_at_utc=user.created_at_utc.isoformat(),
        last_seen_at_utc=user.last_seen_at_utc.isoformat() if user.last_seen_at_utc else None,
    )


class UserRepository:
    """users 表的读写；按令牌摘要查找用户。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_token_hash(self, token_hash: str) -> User | None:
        if not token_hash:
            return None
        row = self._session.scalar(
            select(UserRow).where(UserRow.token_hash == token_hash)
        )
        return _to_user(row) if row is not None else None

    def get(self, user_id: str) -> User | None:
        row = self._session.get(UserRow, user_id)
        return _to_user(row) if row is not None else None

    def add(self, user: User, token_hash: str) -> None:
        row = _to_user_row(user)
        row.token_hash = token_hash
        self._session.add(row)
        self._session.commit()

    def touch(self, user: User, *, at: datetime) -> None:
        row = self._session.get(UserRow, user.id)
        if row is not None:
            row.last_seen_at_utc = at.isoformat()
            self._session.commit()


class PetRepository:
    """pets 表的读写；按 owner 隔离。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, pet_id: str, owner_id: str | None = None) -> Pet | None:
        row = self._session.get(PetRow, pet_id)
        if row is None:
            return None
        if owner_id is not None and row.owner_id != owner_id:
            return None
        return _to_pet(row)

    def list(self, owner_id: str | None = None) -> list[Pet]:
        statement = select(PetRow)
        if owner_id is not None:
            statement = statement.where(PetRow.owner_id == owner_id)
        rows = self._session.scalars(statement.order_by(PetRow.created_at_utc)).all()
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


def _to_alert(row: AlertRow) -> Alert:
    return Alert(
        id=row.id,
        device_id=row.device_id,
        pet_id=row.pet_id,
        kind=row.kind,
        local_date=date.fromisoformat(row.local_date),
        state=row.state,
        image_id=row.image_id,
        confidence=row.confidence,
        created_at_utc=_parse_utc(row.created_at_utc),
        delivered_at_utc=_parse_utc(row.delivered_at_utc) if row.delivered_at_utc else None,
        push_status=row.push_status,
        read_at_utc=_parse_utc(row.read_at_utc) if row.read_at_utc else None,
    )


def _to_alert_row(alert: Alert) -> AlertRow:
    return AlertRow(
        id=alert.id,
        device_id=alert.device_id,
        pet_id=alert.pet_id,
        kind=alert.kind,
        local_date=alert.local_date.isoformat(),
        state=alert.state,
        image_id=alert.image_id,
        confidence=alert.confidence,
        created_at_utc=alert.created_at_utc.isoformat(),
        delivered_at_utc=(
            alert.delivered_at_utc.isoformat() if alert.delivered_at_utc else None
        ),
        read_at_utc=alert.read_at_utc.isoformat() if alert.read_at_utc else None,
        push_status=alert.push_status,
    )


class AlertRepository:
    """alerts 表的读写；同一设备同一天同一类型只保留一条。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, device_id: str, local_date: date, kind: str) -> Alert | None:
        row = self._session.scalar(
            select(AlertRow).where(
                AlertRow.device_id == device_id,
                AlertRow.local_date == local_date.isoformat(),
                AlertRow.kind == kind,
            )
        )
        return _to_alert(row) if row is not None else None

    def get(self, alert_id: str) -> Alert | None:
        row = self._session.get(AlertRow, alert_id)
        return _to_alert(row) if row is not None else None

    def add(self, alert: Alert) -> None:
        self._session.add(_to_alert_row(alert))
        self._session.commit()

    def update(self, alert: Alert) -> None:
        self._session.merge(_to_alert_row(alert))
        self._session.commit()

    def list(
        self,
        *,
        device_id: str | None = None,
        pet_id: str | None = None,
        owner_id: str | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        conditions: list[ColumnElement[bool]] = []
        if device_id is not None:
            conditions.append(AlertRow.device_id == device_id)
        if pet_id is not None:
            # 设备级提醒（pet_id 为空）不属于某只宠物，按宠物筛选时也要带上，
            # 否则用户绑定设备前产生的提醒会在 App 里看不到。
            conditions.append(
                or_(AlertRow.pet_id == pet_id, AlertRow.pet_id.is_(None))
            )
        if owner_id is not None:
            owned = select(PetRow.id).where(PetRow.owner_id == owner_id)
            # 未绑定宠物的设备级提醒（pet_id 为空）对所有人可见。
            conditions.append(
                or_(AlertRow.pet_id.is_(None), AlertRow.pet_id.in_(owned))
            )
        rows = self._session.scalars(
            select(AlertRow)
            .where(*conditions)
            .order_by(AlertRow.created_at_utc.desc(), AlertRow.id)
            .limit(limit)
        ).all()
        return [_to_alert(row) for row in rows]

    def find_recent_delivered(
        self, device_id: str, kind: str, *, since: datetime
    ) -> Alert | None:
        """取该设备在 `since` 之后已成功投递的同类提醒，用于冷却判断。"""
        row = self._session.scalar(
            select(AlertRow)
            .where(
                AlertRow.device_id == device_id,
                AlertRow.kind == kind,
                AlertRow.push_status == "sent",
                AlertRow.delivered_at_utc.is_not(None),
                AlertRow.delivered_at_utc >= since.isoformat(),
            )
            .order_by(AlertRow.delivered_at_utc.desc())
        )
        return _to_alert(row) if row is not None else None

    def clear_image_reference(self, image_id: str) -> None:
        """图片被保留策略清理时保留提醒历史，只解除对图片的引用。"""
        rows = self._session.scalars(
            select(AlertRow).where(AlertRow.image_id == image_id)
        ).all()
        for row in rows:
            row.image_id = None


def _to_push_device(row: PushDeviceRow) -> PushDevice:
    return PushDevice(
        id=row.id,
        device_id=row.device_id,
        pet_id=row.pet_id,
        expo_push_token=row.expo_push_token,
        platform=row.platform,
        created_at_utc=_parse_utc(row.created_at_utc),
        updated_at_utc=_parse_utc(row.updated_at_utc),
        owner_id=row.owner_id,
    )


def _to_push_device_row(device: PushDevice) -> PushDeviceRow:
    return PushDeviceRow(
        id=device.id,
        device_id=device.device_id,
        pet_id=device.pet_id,
        expo_push_token=device.expo_push_token,
        platform=device.platform,
        created_at_utc=device.created_at_utc.isoformat(),
        updated_at_utc=device.updated_at_utc.isoformat(),
        owner_id=device.owner_id,
    )


class PushDeviceRepository:
    """push_devices 表的读写；token 唯一。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_token(self, token: str) -> PushDevice | None:
        row = self._session.scalar(
            select(PushDeviceRow).where(PushDeviceRow.expo_push_token == token)
        )
        return _to_push_device(row) if row is not None else None

    def get(self, device_pk: str) -> PushDevice | None:
        row = self._session.get(PushDeviceRow, device_pk)
        return _to_push_device(row) if row is not None else None

    def upsert(self, device: PushDevice) -> PushDevice:
        """按 token 覆盖；已存在时保留原主键只更新绑定关系。"""
        row = self._session.scalar(
            select(PushDeviceRow).where(
                PushDeviceRow.expo_push_token == device.expo_push_token
            )
        )
        if row is None:
            self._session.add(_to_push_device_row(device))
            self._session.commit()
            return device

        row.device_id = device.device_id
        row.pet_id = device.pet_id
        row.platform = device.platform
        row.updated_at_utc = device.updated_at_utc.isoformat()
        if device.owner_id is not None:
            row.owner_id = device.owner_id
        self._session.commit()
        self._session.refresh(row)
        return _to_push_device(row)

    def list_for(
        self, *, device_id: str | None, pet_id: str | None
    ) -> list[PushDevice]:
        """按设备号或宠物号匹配推送目标（任一命中即可）。"""
        conditions: list[ColumnElement[bool]] = []
        if device_id is not None:
            conditions.append(PushDeviceRow.device_id == device_id)
        if pet_id is not None:
            conditions.append(PushDeviceRow.pet_id == pet_id)
        if not conditions:
            return []
        rows = self._session.scalars(
            select(PushDeviceRow)
            .where(or_(*conditions))
            .order_by(PushDeviceRow.created_at_utc)
        ).all()
        return [_to_push_device(row) for row in rows]

    def list_device_ids(self) -> list[str]:
        """所有注册过的设备号（去重、非空），供健康扫描遍历。"""
        rows = self._session.scalars(
            select(PushDeviceRow.device_id)
            .where(PushDeviceRow.device_id.is_not(None))
            .distinct()
        ).all()
        return [value for value in rows if value]

    def pet_for_device(self, device_id: str) -> str | None:
        """取绑定到该设备号的第一个宠物；用于给提醒补 `pet_id`。"""
        row = self._session.scalar(
            select(PushDeviceRow).where(
                PushDeviceRow.device_id == device_id,
                PushDeviceRow.pet_id.is_not(None),
            )
        )
        return row.pet_id if row is not None else None

    def delete(self, device_pk: str) -> bool:
        row = self._session.get(PushDeviceRow, device_pk)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    def device_for_pet(self, pet_id: str) -> str | None:
        """取绑定到该宠物的第一个设备号；用于按宠物生成萌照。"""
        row = self._session.scalar(
            select(PushDeviceRow).where(
                PushDeviceRow.pet_id == pet_id,
                PushDeviceRow.device_id.is_not(None),
            )
        )
        return row.device_id if row is not None else None


def _to_portrait_setting(row: PortraitSettingRow) -> PortraitSetting:
    return PortraitSetting(
        pet_id=row.pet_id,
        enabled=bool(row.enabled),
        per_day=row.per_day,
        start_hour=row.start_hour,
        end_hour=row.end_hour,
        updated_at_utc=_parse_utc(row.updated_at_utc),
    )


def _to_portrait_shot(row: PortraitShotRow) -> PortraitShot:
    return PortraitShot(
        id=row.id,
        device_id=row.device_id,
        pet_id=row.pet_id,
        local_date=date.fromisoformat(row.local_date),
        slot=row.slot,
        source_image_id=row.source_image_id,
        rel_path=row.rel_path,
        width=row.width,
        height=row.height,
        score=row.score,
        created_at_utc=_parse_utc(row.created_at_utc),
    )


def _parse_box(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = [int(chunk) for chunk in value.split(",")]
    if len(parts) != 4:
        return None
    return (parts[0], parts[1], parts[2], parts[3])


def _format_box(box: tuple[int, int, int, int] | None) -> str | None:
    if box is None:
        return None
    return ",".join(str(value) for value in box)


def _to_portrait_feedback(row: PortraitFeedbackRow) -> PortraitFeedback:
    return PortraitFeedback(
        id=row.id,
        shot_id=row.shot_id,
        owner_id=row.owner_id,
        kind=row.kind,
        crop_box=_parse_box(row.crop_box),
        created_at_utc=_parse_utc(row.created_at_utc),
    )


class PortraitSettingRepository:
    """portrait_settings 表的读写；缺行时由服务层套默认值。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, pet_id: str) -> PortraitSetting | None:
        row = self._session.get(PortraitSettingRow, pet_id)
        return _to_portrait_setting(row) if row is not None else None

    def upsert(self, setting: PortraitSetting) -> PortraitSetting:
        row = self._session.get(PortraitSettingRow, setting.pet_id)
        if row is None:
            row = PortraitSettingRow(
                pet_id=setting.pet_id,
                enabled=setting.enabled,
                per_day=setting.per_day,
                start_hour=setting.start_hour,
                end_hour=setting.end_hour,
                updated_at_utc=setting.updated_at_utc.isoformat(),
            )
            self._session.add(row)
        else:
            row.enabled = setting.enabled
            row.per_day = setting.per_day
            row.start_hour = setting.start_hour
            row.end_hour = setting.end_hour
            row.updated_at_utc = setting.updated_at_utc.isoformat()
        self._session.commit()
        self._session.refresh(row)
        return _to_portrait_setting(row)

    def delete_for_pet(self, pet_id: str) -> None:
        row = self._session.get(PortraitSettingRow, pet_id)
        if row is not None:
            self._session.delete(row)
            self._session.commit()


class PortraitShotRepository:
    """portrait_shots 表的读写；同设备同天同槽位唯一。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, shot_id: str) -> PortraitShot | None:
        row = self._session.get(PortraitShotRow, shot_id)
        return _to_portrait_shot(row) if row is not None else None

    def find_slot(self, device_id: str, local_date: date, slot: int) -> PortraitShot | None:
        row = self._session.scalar(
            select(PortraitShotRow).where(
                PortraitShotRow.device_id == device_id,
                PortraitShotRow.local_date == local_date.isoformat(),
                PortraitShotRow.slot == slot,
            )
        )
        return _to_portrait_shot(row) if row is not None else None

    def count_for_date(self, device_id: str, local_date: date) -> int:
        total = self._session.scalar(
            select(func.count())
            .select_from(PortraitShotRow)
            .where(
                PortraitShotRow.device_id == device_id,
                PortraitShotRow.local_date == local_date.isoformat(),
            )
        )
        return int(total or 0)

    def source_ids(self, device_id: str, local_date: date) -> set[str]:
        """当天已经被用掉的源图 id，避免同一天重复用同一张。"""
        rows = self._session.scalars(
            select(PortraitShotRow.source_image_id).where(
                PortraitShotRow.device_id == device_id,
                PortraitShotRow.local_date == local_date.isoformat(),
                PortraitShotRow.source_image_id.is_not(None),
            )
        ).all()
        return {value for value in rows if value}

    def add(self, shot: PortraitShot) -> PortraitShot:
        self._session.add(
            PortraitShotRow(
                id=shot.id,
                device_id=shot.device_id,
                pet_id=shot.pet_id,
                local_date=shot.local_date.isoformat(),
                slot=shot.slot,
                source_image_id=shot.source_image_id,
                rel_path=shot.rel_path,
                width=shot.width,
                height=shot.height,
                score=shot.score,
                dhash="",
                created_at_utc=shot.created_at_utc.isoformat(),
            )
        )
        self._session.commit()
        return shot

    def save_hash(self, shot_id: str, digest: str) -> None:
        row = self._session.get(PortraitShotRow, shot_id)
        if row is not None:
            row.dhash = digest
            self._session.commit()

    def recent_hashes(self, device_id: str, *, limit: int = 7) -> list[str]:
        rows = self._session.scalars(
            select(PortraitShotRow.dhash)
            .where(PortraitShotRow.device_id == device_id, PortraitShotRow.dhash != "")
            .order_by(PortraitShotRow.created_at_utc.desc())
            .limit(limit)
        ).all()
        return [value for value in rows if value]

    def list_for_pet(
        self, pet_id: str, *, local_date: date | None = None, limit: int = 30
    ) -> list[PortraitShot]:
        statement = select(PortraitShotRow).where(PortraitShotRow.pet_id == pet_id)
        if local_date is not None:
            statement = statement.where(
                PortraitShotRow.local_date == local_date.isoformat()
            )
        rows = self._session.scalars(
            statement.order_by(PortraitShotRow.created_at_utc.desc()).limit(limit)
        ).all()
        return [_to_portrait_shot(row) for row in rows]

    def latest_for_pet(self, pet_id: str) -> PortraitShot | None:
        row = self._session.scalar(
            select(PortraitShotRow)
            .where(PortraitShotRow.pet_id == pet_id)
            .order_by(PortraitShotRow.created_at_utc.desc())
            .limit(1)
        )
        return _to_portrait_shot(row) if row is not None else None

    def delete_for_pet(self, pet_id: str) -> None:
        for row in self._session.scalars(
            select(PortraitShotRow).where(PortraitShotRow.pet_id == pet_id)
        ).all():
            self._session.delete(row)
        self._session.commit()


class PortraitFeedbackRepository:
    """portrait_feedback 表的读写；同张照的同类反馈只留一条。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, shot_id: str, kind: str) -> PortraitFeedback | None:
        row = self._session.scalar(
            select(PortraitFeedbackRow).where(
                PortraitFeedbackRow.shot_id == shot_id,
                PortraitFeedbackRow.kind == kind,
            )
        )
        return _to_portrait_feedback(row) if row is not None else None

    def add(self, feedback: PortraitFeedback) -> PortraitFeedback:
        existing = self.find(feedback.shot_id, feedback.kind)
        if existing is not None:
            return existing
        self._session.add(
            PortraitFeedbackRow(
                id=feedback.id,
                shot_id=feedback.shot_id,
                owner_id=feedback.owner_id,
                kind=feedback.kind,
                crop_box=_format_box(feedback.crop_box),
                created_at_utc=feedback.created_at_utc.isoformat(),
            )
        )
        self._session.commit()
        return feedback

    def list_for_shot(self, shot_id: str) -> list[PortraitFeedback]:
        rows = self._session.scalars(
            select(PortraitFeedbackRow)
            .where(PortraitFeedbackRow.shot_id == shot_id)
            .order_by(PortraitFeedbackRow.created_at_utc)
        ).all()
        return [_to_portrait_feedback(row) for row in rows]

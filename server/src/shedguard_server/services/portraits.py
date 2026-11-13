"""萌照：选片、生成、反馈与定时扫描。

分工：
- `domain/portrait.py` 负责「够不够格、谁最好、裁成什么样」；
- 本模块负责取数据、落盘、写表、发提醒；
- 定时循环在 `app.py` 里，调 `scan_once`。
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.alerts import Alert
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.portrait import (
    ALERT_KIND_PORTRAIT,
    DEFAULT_END_HOUR,
    DEFAULT_MAX_HIGHLIGHT,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_SUBJECT_RATIO,
    DEFAULT_PER_DAY,
    DEFAULT_START_HOUR,
    Candidate,
    PortraitFeedback,
    PortraitSetting,
    PortraitShot,
    crop_square,
    difference_hash,
    encode_square,
    is_near_duplicate,
    portrait_rel_path,
    rank_candidates,
    square_crop_box,
)
from shedguard_server.domain.push import PushGateway
from shedguard_server.errors import InvalidRequestError, NotFoundError
from shedguard_server.infra.imaging import decode_image
from shedguard_server.infra.repository import (
    AlertRepository,
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    PortraitFeedbackRepository,
    PortraitSettingRepository,
    PortraitShotRepository,
    PushDeviceRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.alerts import AlertService

DEFAULT_OUTPUT_PX = 640
DEFAULT_JPEG_QUALITY = 88


def _local_now(timezone: str, now: datetime | None) -> datetime:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(timezone))


class PortraitService:
    """萌照的读取与生成。"""

    def __init__(
        self,
        *,
        portraits: PortraitShotRepository,
        feedback: PortraitFeedbackRepository,
        settings: PortraitSettingRepository,
        pets: PetRepository,
        devices: PushDeviceRepository,
        images: ImageRepository,
        metrics: FrameMetricRepository,
        storage: LocalStorage,
        output_px: int = DEFAULT_OUTPUT_PX,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        min_subject_ratio: float = DEFAULT_MIN_SUBJECT_RATIO,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_highlight: float = DEFAULT_MAX_HIGHLIGHT,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._portraits = portraits
        self._feedback = feedback
        self._settings = settings
        self._pets = pets
        self._devices = devices
        self._images = images
        self._metrics = metrics
        self._storage = storage
        self._output_px = output_px
        self._jpeg_quality = jpeg_quality
        self._min_subject_ratio = min_subject_ratio
        self._min_confidence = min_confidence
        self._max_highlight = max_highlight
        self._timezone = timezone

    # ---- 设置 ----

    def _require_pet(self, pet_id: str, owner_id: str | None) -> None:
        if self._pets.find(pet_id, owner_id) is None:
            msg = f"宠物不存在: {pet_id}"
            raise NotFoundError(msg)

    def get_settings(self, pet_id: str, *, owner_id: str | None = None) -> PortraitSetting:
        self._require_pet(pet_id, owner_id)
        stored = self._settings.get(pet_id)
        if stored is not None:
            return stored
        return PortraitSetting(
            pet_id=pet_id,
            enabled=True,
            per_day=DEFAULT_PER_DAY,
            start_hour=DEFAULT_START_HOUR,
            end_hour=DEFAULT_END_HOUR,
            updated_at_utc=datetime.now(UTC),
        )

    def update_settings(
        self,
        pet_id: str,
        *,
        owner_id: str | None = None,
        enabled: bool | None = None,
        per_day: int | None = None,
        start_hour: int | None = None,
        end_hour: int | None = None,
        now: datetime | None = None,
    ) -> PortraitSetting:
        self._require_pet(pet_id, owner_id)
        current = self.get_settings(pet_id, owner_id=owner_id)
        try:
            # ``replace`` 会重新执行 ``__post_init__``，非法窗口在构造时就抛 ValueError。
            candidate = replace(
                current,
                enabled=current.enabled if enabled is None else enabled,
                per_day=current.per_day if per_day is None else per_day,
                start_hour=current.start_hour if start_hour is None else start_hour,
                end_hour=current.end_hour if end_hour is None else end_hour,
                updated_at_utc=now or datetime.now(UTC),
            )
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self._settings.upsert(candidate)

    # ---- 读取 ----

    def list_for_pet(
        self,
        pet_id: str,
        *,
        owner_id: str | None = None,
        local_date: date | None = None,
        limit: int = 30,
    ) -> list[PortraitShot]:
        self._require_pet(pet_id, owner_id)
        return self._portraits.list_for_pet(pet_id, local_date=local_date, limit=limit)

    def today(
        self, pet_id: str, *, owner_id: str | None = None, now: datetime | None = None
    ) -> list[PortraitShot]:
        local = _local_now(self._timezone, now).date()
        return self.list_for_pet(pet_id, owner_id=owner_id, local_date=local, limit=6)

    def get_shot(self, shot_id: str, *, owner_id: str | None = None) -> PortraitShot:
        shot = self._portraits.get(shot_id)
        if shot is None:
            msg = f"萌照不存在: {shot_id}"
            raise NotFoundError(msg)
        if shot.pet_id is not None:
            self._require_pet(shot.pet_id, owner_id)
        return shot

    def read_image(self, shot_id: str, *, owner_id: str | None = None) -> bytes:
        shot = self.get_shot(shot_id, owner_id=owner_id)
        return self._storage.read(shot.rel_path)

    # ---- 生成 ----

    def _candidates(
        self, device_id: str, local_date: date, *, skip_image_ids: set[str]
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        for record in self._images.list_for_range(device_id, local_date, local_date):
            if record.id in skip_image_ids:
                continue
            metric = self._metrics.find(record.id)
            if metric is None or not metric.detected or metric.box is None:
                continue
            try:
                frame = decode_image(self._storage.read(record.rel_path))
            except Exception:  # 单张坏图不该打断选片
                continue
            candidates.append(
                Candidate(
                    image_id=record.id,
                    box=metric.box,
                    detector_confidence=metric.detector_confidence,
                    edge_density=metric.edge_density,
                    high_light_ratio=metric.high_light_ratio,
                    width=frame.width,
                    height=frame.height,
                )
            )
        return candidates

    def existing(self, device_id: str, local_date: date, slot: int) -> PortraitShot | None:
        """某设备某天第 `slot` 张是否已经生成过。"""
        return self._portraits.find_slot(device_id, local_date, slot)

    def generate(
        self,
        device_id: str,
        *,
        local_date: date,
        pet_id: str | None,
        slot: int = 0,
        now: datetime | None = None,
    ) -> PortraitShot | None:
        """为某设备某天生成第 `slot` 张萌照；没有合格图时返回 None。"""
        existing = self._portraits.find_slot(device_id, local_date, slot)
        if existing is not None:
            return existing

        used = self._portraits.source_ids(device_id, local_date)
        candidates = self._candidates(device_id, local_date, skip_image_ids=used)
        ranked = rank_candidates(
            candidates,
            min_subject_ratio=self._min_subject_ratio,
            min_confidence=self._min_confidence,
            max_highlight=self._max_highlight,
        )
        if not ranked:
            return None

        recent_hashes = self._portraits.recent_hashes(device_id)
        chosen = None
        digest = ""
        for item in ranked:
            record = self._images.find_by_id(item.candidate.image_id)
            if record is None:
                continue
            try:
                frame: ImageFrame = decode_image(self._storage.read(record.rel_path))
            except Exception:  # 坏图跳过，继续下一张
                continue
            box = square_crop_box(item.candidate.box or (0, 0, 1, 1), frame.width, frame.height)
            square = crop_square(frame, box)
            digest = difference_hash(square)
            if any(
                is_near_duplicate(digest, previous) for previous in recent_hashes
            ):
                continue
            chosen = (item, square)
            break

        if chosen is None:
            return None

        item, square = chosen
        shot_id = str(uuid.uuid4())
        rel_path = portrait_rel_path(local_date, device_id, shot_id)
        payload = encode_square(
            square, output_px=self._output_px, quality=self._jpeg_quality
        )
        self._storage.write_atomic(rel_path, payload)
        shot = PortraitShot(
            id=shot_id,
            device_id=device_id,
            pet_id=pet_id,
            local_date=local_date,
            slot=slot,
            source_image_id=item.candidate.image_id,
            rel_path=rel_path,
            width=square.width,
            height=square.height,
            score=item.score,
            created_at_utc=now or datetime.now(UTC),
        )
        self._portraits.add(shot)
        self._portraits.save_hash(shot_id, digest)
        return shot

    def add_feedback(
        self,
        shot_id: str,
        *,
        owner_id: str | None = None,
        kind: str,
        crop_box: tuple[int, int, int, int] | None = None,
        now: datetime | None = None,
    ) -> PortraitFeedback:
        shot = self.get_shot(shot_id, owner_id=owner_id)
        try:
            feedback = PortraitFeedback(
                id=str(uuid.uuid4()),
                shot_id=shot.id,
                owner_id=owner_id,
                kind=kind,
                crop_box=crop_box,
                created_at_utc=now or datetime.now(UTC),
            )
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
        return self._feedback.add(feedback)


def slot_time(setting: PortraitSetting, slot: int) -> datetime:
    """第 `slot` 张的计划时刻（当天本地时间，无时区）。"""
    span = setting.end_hour - setting.start_hour
    step = span / max(1, setting.per_day)
    return datetime(2000, 1, 1, setting.start_hour) + timedelta(hours=step * slot)


def scan_once(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    storage: LocalStorage,
    gateway: PushGateway,
    now: datetime | None = None,
) -> int:
    """按宠物设置生成到期萌照，返回本次新生成的张数。"""
    if not settings.portrait_enabled:
        return 0
    moment = now or datetime.now(UTC)
    local_now = _local_now(settings.timezone, moment)
    created = 0
    with session_factory() as session:
        pets = PetRepository(session)
        devices = PushDeviceRepository(session)
        alerts = AlertService(
            AlertRepository(session),
            devices,
            gateway,
            cooldown_hours=settings.alert_cooldown_hours,
        )
        service = PortraitService(
            portraits=PortraitShotRepository(session),
            feedback=PortraitFeedbackRepository(session),
            settings=PortraitSettingRepository(session),
            pets=pets,
            devices=devices,
            images=ImageRepository(session),
            metrics=FrameMetricRepository(session),
            storage=storage,
            output_px=settings.portrait_max_output_px,
            jpeg_quality=settings.portrait_jpeg_quality,
            min_subject_ratio=settings.portrait_min_subject_ratio,
            min_confidence=settings.portrait_min_detector_confidence,
            timezone=settings.timezone,
        )
        for pet in pets.list():
            setting = service.get_settings(pet.id)
            if not setting.enabled or setting.per_day <= 0:
                continue
            device_id = devices.device_for_pet(pet.id)
            if device_id is None:
                continue
            for slot in range(setting.per_day):
                due = slot_time(setting, slot)
                if local_now.time() < due.time():
                    break
                if service.existing(device_id, local_now.date(), slot) is not None:
                    # 这一档已经生成过，后面的档位还没到期，直接等下一轮扫描。
                    break
                shot = service.generate(
                    device_id,
                    local_date=local_now.date(),
                    pet_id=pet.id,
                    slot=slot,
                    now=moment,
                )
                if shot is None:
                    break
                created += 1
                if slot == 0:
                    _notify(alerts, shot, pet_id=pet.id, now=moment)
    return created


def _notify(
    alerts: AlertService, shot: PortraitShot, *, pet_id: str | None, now: datetime
) -> None:
    """萌照提醒沿用 alerts；每天只建一条（唯一键是设备+日期+类型）。"""
    created: Alert | None = alerts.create_alert(
        device_id=shot.device_id,
        local_date=shot.local_date,
        kind=ALERT_KIND_PORTRAIT,
        state="",
        image_id=shot.source_image_id,
        confidence=None,
        pet_id=pet_id,
        now=now,
    )
    if created is not None:
        alerts.deliver(created, now=now)


__all__ = [
    "ALERT_KIND_PORTRAIT",
    "PortraitService",
    "scan_once",
    "slot_time",
]
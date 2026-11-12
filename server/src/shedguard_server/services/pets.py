"""宠物、蜕皮日志与拍照查验的业务编排。"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from shedguard_server.domain.models import SheddingState
from shedguard_server.domain.pets import (
    Pet,
    PetCheckResult,
    ShedPrediction,
    ShedRecord,
)
from shedguard_server.errors import ConflictError, InvalidRequestError, NotFoundError
from shedguard_server.ids import new_request_id
from shedguard_server.infra.repository import PetRepository, ShedRecordRepository

MAX_NAME_LENGTH = 64
MAX_NOTES_LENGTH = 2000
MAX_PETS = 20

ADVICE_BY_STATE: dict[str, str] = {
    "normal": (
        "守宫当前皮肤状态正常。保持饲养箱湿度稳定，提供湿润躲避穴，"
        "蜕皮自然来临时它会自己处理。"
    ),
    "shedding": (
        "守宫正在蜕皮。保持饲养箱湿度在 50% 以上，提供湿润躲避穴，"
        "切勿强行撕扯皮肤；若 48 小时后仍有残留，用温水浸泡后再用棉签轻敷。"
    ),
    "opaque": (
        "守宫皮肤开始蒙白发暗，蜕皮临近。提高饲养箱湿度，检查躲避穴是否湿润，"
        "暂时减少上手把玩，等待皮肤自然脱落。"
    ),
    "unknown": (
        "无法判断当前状态。请在光线充足的环境下，对准守宫全身重新拍摄一张。"
    ),
}


class _UploadOutcomeLike(Protocol):
    """ingest 的返回值只需要 record 字段。"""

    @property
    def record(self) -> Any: ...


class _IngestLike(Protocol):
    """IngestService.ingest 的最小接口；拍照查验要复用它落图。"""

    def ingest(
        self,
        payload: bytes,
        *,
        device_id_raw: str | None,
        captured_at_raw: str | None,
    ) -> _UploadOutcomeLike: ...


class _SheddingLike(Protocol):
    """SheddingService.analyze 的最小接口。"""

    def analyze(self, image_id: str, *, now: datetime | None = None) -> SheddingState: ...


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def _mad(values: list[int], median: int) -> int:
    return _median([abs(v - median) for v in values])


def predict_next_shed(records: list[ShedRecord], *, today: date) -> ShedPrediction:
    """从已完成蜕皮记录推导下次蜕皮窗口。

    规则（规格 4.3 节）：至少 2 个完整间隔才可预测；
    窗口 = 最后一次蜕皮开始日 + (中位间隔 - MAD) 到 (中位间隔 + MAD)。
    """
    completed = [r for r in records if r.completed_on is not None]
    completed.sort(key=lambda r: r.started_on)
    if len(completed) < 3:
        return ShedPrediction(
            predictable=False,
            reason=f"已记录 {len(completed)} 次完整蜕皮，至少需要 3 次才能计算周期",
        )
    intervals: list[int] = []
    for prev, curr in itertools.pairwise(completed):
        gap = (curr.started_on - prev.started_on).days
        if gap > 0:
            intervals.append(gap)
    if len(intervals) < 2:
        return ShedPrediction(
            predictable=False,
            reason="完整间隔不足 2 个，暂时无法预测",
        )
    median = _median(intervals)
    mad = _mad(intervals, median)
    last = completed[-1]
    window_start = last.started_on + timedelta(days=max(median - mad, 1))
    window_end = last.started_on + timedelta(days=median + mad)
    if window_end < today:
        return ShedPrediction(
            predictable=False,
            reason="预测窗口已过，请确认最近一次蜕皮是否已记录",
        )
    return ShedPrediction(
        predictable=True,
        reason="基于历史蜕皮间隔的中位数与偏差",
        median_interval_days=median,
        mad_days=mad,
        next_window_start=window_start,
        next_window_end=window_end,
        based_on_cycles=len(intervals),
    )


class PetService:
    """宠物档案 CRUD。"""

    def __init__(self, pets: PetRepository, records: ShedRecordRepository) -> None:
        self._pets = pets
        self._records = records

    def _validate_name(self, name: str) -> str:
        stripped = name.strip()
        if not stripped:
            raise InvalidRequestError("宠物名字不能为空")
        if len(stripped) > MAX_NAME_LENGTH:
            raise InvalidRequestError(f"宠物名字不能超过 {MAX_NAME_LENGTH} 个字符")
        return stripped

    def list(self, *, owner_id: str | None = None) -> list[Pet]:
        return self._pets.list(owner_id)

    def get(self, pet_id: str, *, owner_id: str | None = None) -> Pet:
        pet = self._pets.find(pet_id, owner_id)
        if pet is None:
            raise NotFoundError(f"宠物不存在: {pet_id}")
        return pet

    def create(
        self,
        *,
        name: str,
        species: str = "豹纹守宫",
        morph: str | None = None,
        birth_date: date | None = None,
        owner_id: str | None = None,
    ) -> Pet:
        valid_name = self._validate_name(name)
        if len(self._pets.list(owner_id)) >= MAX_PETS:
            raise InvalidRequestError(f"宠物数量已达上限 {MAX_PETS}")
        now = datetime.now(UTC)
        pet = Pet(
            id=new_request_id(),
            name=valid_name,
            species=species.strip() or "豹纹守宫",
            morph=morph.strip() if morph else None,
            birth_date=birth_date,
            created_at_utc=now,
            updated_at_utc=now,
            owner_id=owner_id,
        )
        self._pets.add(pet)
        return pet

    def update(
        self,
        pet_id: str,
        *,
        name: str | None = None,
        species: str | None = None,
        morph: str | None = None,
        birth_date: date | None = None,
        owner_id: str | None = None,
    ) -> Pet:
        pet = self.get(pet_id, owner_id=owner_id)
        new_name = self._validate_name(name) if name is not None else pet.name
        new_species = pet.species
        if species is not None and species.strip():
            new_species = species.strip()
        new_morph = pet.morph
        if morph is not None:
            new_morph = morph.strip() or None
        new_birth = birth_date if birth_date is not None else pet.birth_date
        if (
            new_name == pet.name
            and new_species == pet.species
            and new_morph == pet.morph
            and new_birth == pet.birth_date
        ):
            return pet
        updated = Pet(
            id=pet.id,
            name=new_name,
            species=new_species,
            morph=new_morph,
            birth_date=new_birth,
            created_at_utc=pet.created_at_utc,
            updated_at_utc=datetime.now(UTC),
            owner_id=pet.owner_id,
        )
        self._pets.update(updated)
        return updated

    def delete(self, pet_id: str, *, owner_id: str | None = None) -> None:
        pet = self.get(pet_id, owner_id=owner_id)
        self._records.delete_for_pet(pet.id)
        self._pets.delete(pet.id)


class ShedRecordService:
    """手动蜕皮日志 CRUD 与周期预测。"""

    def __init__(self, pets: PetRepository, records: ShedRecordRepository) -> None:
        self._pets = pets
        self._records = records

    def _get_pet(self, pet_id: str, *, owner_id: str | None = None) -> Pet:
        pet = self._pets.find(pet_id, owner_id)
        if pet is None:
            raise NotFoundError(f"宠物不存在: {pet_id}")
        return pet

    def list_for_pet(self, pet_id: str, *, owner_id: str | None = None) -> list[ShedRecord]:
        self._get_pet(pet_id, owner_id=owner_id)
        return self._records.list_for_pet(pet_id)

    def create(
        self,
        pet_id: str,
        *,
        started_on: date,
        completed_on: date | None = None,
        notes: str | None = None,
        owner_id: str | None = None,
    ) -> ShedRecord:
        self._get_pet(pet_id, owner_id=owner_id)
        if completed_on is not None and completed_on < started_on:
            raise InvalidRequestError("完成日期不能早于开始日期")
        if notes and len(notes) > MAX_NOTES_LENGTH:
            raise InvalidRequestError(f"备注不能超过 {MAX_NOTES_LENGTH} 个字符")
        existing = self._records.find_by_started_on(pet_id, started_on)
        if existing is not None:
            raise ConflictError(f"{started_on.isoformat()} 已有蜕皮记录，请直接编辑那条")
        now = datetime.now(UTC)
        record = ShedRecord(
            id=new_request_id(),
            pet_id=pet_id,
            started_on=started_on,
            completed_on=completed_on,
            notes=notes.strip() if notes else None,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._records.add(record)
        return record

    def update(
        self,
        pet_id: str,
        record_id: str,
        *,
        started_on: date | None = None,
        completed_on: date | None = None,
        notes: str | None = None,
        owner_id: str | None = None,
    ) -> ShedRecord:
        self._get_pet(pet_id, owner_id=owner_id)
        record = self._records.find(record_id)
        if record is None or record.pet_id != pet_id:
            raise NotFoundError(f"蜕皮记录不存在: {record_id}")
        new_started = started_on or record.started_on
        new_completed = completed_on if completed_on is not None else record.completed_on
        if new_completed is not None and new_completed < new_started:
            raise InvalidRequestError("完成日期不能早于开始日期")
        if new_started != record.started_on:
            existing = self._records.find_by_started_on(pet_id, new_started)
            if existing is not None and existing.id != record.id:
                raise ConflictError(
                    f"{new_started.isoformat()} 已有蜕皮记录，请直接编辑那条"
                )
        updated = ShedRecord(
            id=record.id,
            pet_id=record.pet_id,
            started_on=new_started,
            completed_on=new_completed,
            notes=notes.strip() if notes else record.notes,
            created_at_utc=record.created_at_utc,
            updated_at_utc=datetime.now(UTC),
        )
        self._records.update(updated)
        return updated

    def delete(
        self, pet_id: str, record_id: str, *, owner_id: str | None = None
    ) -> None:
        self._get_pet(pet_id, owner_id=owner_id)
        record = self._records.find(record_id)
        if record is None or record.pet_id != pet_id:
            raise NotFoundError(f"蜕皮记录不存在: {record_id}")
        self._records.delete(record_id)

    def predict(
        self, pet_id: str, *, today: date | None = None, owner_id: str | None = None
    ) -> ShedPrediction:
        self._get_pet(pet_id, owner_id=owner_id)
        records = self._records.list_for_pet(pet_id)
        return predict_next_shed(records, today=today or datetime.now(UTC).date())


class CheckPhotoService:
    """拍照查验：上传 → 分类 → 建议，一步完成。"""

    def __init__(self, pets: PetRepository, ingest: _IngestLike, shedding: _SheddingLike) -> None:
        self._pets = pets
        self._ingest = ingest
        self._shedding = shedding

    def check(
        self,
        pet_id: str,
        payload: bytes,
        *,
        now: datetime | None = None,
        owner_id: str | None = None,
    ) -> PetCheckResult:
        pet = self._pets.find(pet_id, owner_id)
        if pet is None:
            raise NotFoundError(f"宠物不存在: {pet_id}")
        if not payload:
            raise InvalidRequestError("图片内容为空")
        moment = now or datetime.now(UTC)
        outcome = self._ingest.ingest(
            payload,
            device_id_raw=f"pet-{pet.id}",
            captured_at_raw=moment.isoformat(),
        )
        record = outcome.record
        image_id = str(record.id)
        state_obj = self._shedding.analyze(image_id, now=moment)
        advice = ADVICE_BY_STATE.get(state_obj.state, ADVICE_BY_STATE["unknown"])
        return PetCheckResult(
            image_id=image_id,
            state=state_obj.state,
            confidence=state_obj.confidence,
            probabilities=state_obj.probabilities,
            advice=advice,
        )

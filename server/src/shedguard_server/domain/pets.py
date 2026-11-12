"""宠物与手动蜕皮日志的领域对象。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Pet:
    """一只被记录的守宫。"""

    id: str
    name: str
    species: str
    morph: str | None
    birth_date: date | None
    created_at_utc: datetime
    updated_at_utc: datetime
    owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShedRecord:
    """一次手动记录的蜕皮。"""

    id: str
    pet_id: str
    started_on: date
    completed_on: date | None
    notes: str | None
    created_at_utc: datetime
    updated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ShedPrediction:
    """基于历史蜕皮记录的下次蜕皮窗口预测。

    `predictable` 为 False 时其余字段无意义，`reason` 解释原因。
    """

    predictable: bool
    reason: str
    median_interval_days: int | None = None
    mad_days: int | None = None
    next_window_start: date | None = None
    next_window_end: date | None = None
    based_on_cycles: int = 0


@dataclass(frozen=True, slots=True)
class PetCheckResult:
    """一次拍照查验的聚合结果。"""

    image_id: str
    state: str
    confidence: float | None
    probabilities: dict[str, float] | None
    advice: str

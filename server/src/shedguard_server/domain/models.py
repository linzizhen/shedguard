"""领域值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ImageRecord:
    """一张已入库图片的完整元数据。"""

    id: str
    device_id: str
    rel_path: str
    byte_size: int
    sha256: str
    captured_at_utc: datetime
    local_date: date
    received_at_utc: datetime


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    """上传结果；`duplicate` 表示同一内容此前已入库。"""

    record: ImageRecord
    duplicate: bool


@dataclass(frozen=True, slots=True)
class ImagePage:
    """按日期分页查询的结果。"""

    items: list[ImageRecord]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class DailyFrame:
    """某一天的代表帧；`image_id` 为 None 表示该日缺失。"""

    local_date: date
    image_id: str | None
    captured_at_utc: datetime | None
    in_window: bool
    total_images: int


@dataclass(frozen=True, slots=True)
class ShedEvent:
    """一次蜕皮记录。"""

    id: str
    device_id: str
    event_date: date
    outcome: str
    notes: str | None
    created_at_utc: datetime
    updated_at_utc: datetime
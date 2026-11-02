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
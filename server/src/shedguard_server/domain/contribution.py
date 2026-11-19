"""数据贡献的纯逻辑层：命名、路径、元数据白名单、编码与上传载荷。

这里只放**不碰数据库、不碰文件系统**的东西，方便单测与复用。
真正落盘、读库、调上传器在 `services/contributions.py`。
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final

import cv2

from shedguard_server.domain.imaging import ImageFrame

# —— 采集上限 ————————————————————————————————————————————————

DEFAULT_PER_EVENT_LIMIT: Final = 3
MAX_PER_EVENT_LIMIT: Final = 10
DEFAULT_MAX_PENDING: Final = 200
MIN_MAX_PENDING: Final = 10
MAX_MAX_PENDING: Final = 5000

# —— 图片处理 ————————————————————————————————————————————————

DEFAULT_CROP_PADDING: Final = 0.08
CROP_JPEG_QUALITY: Final = 88
FULL_JPEG_QUALITY: Final = 85
DEVICE_HASH_LENGTH: Final = 12
SHA_PREFIX_LENGTH: Final = 12

# —— 样本状态 ————————————————————————————————————————————————

SAMPLE_PENDING: Final = "pending"
SAMPLE_UPLOADED: Final = "uploaded"
SAMPLE_FAILED: Final = "failed"
SAMPLE_WITHDRAWN: Final = "withdrawn"
SAMPLE_STATUSES: Final = frozenset(
    {SAMPLE_PENDING, SAMPLE_UPLOADED, SAMPLE_FAILED, SAMPLE_WITHDRAWN}
)
RETRYABLE_STATUSES: Final = frozenset({SAMPLE_PENDING, SAMPLE_FAILED})
MAX_UPLOAD_ATTEMPTS: Final = 5

# —— 默认值 ————————————————————————————————————————————————

DEFAULT_CONTRIBUTION_ENABLED: Final = False
DEFAULT_INCLUDE_FULL: Final = False

#: 远端元数据只允许出现这些字段——测试会钉住它，防止哪天顺手把宠物名写进去。
META_FIELDS: Final = (
    "sha12",
    "state",
    "confidence",
    "local_date",
    "has_full",
    "width",
    "height",
)


def device_hash(device_id: str) -> str:
    """设备号 → 不可反查的分组哈希（远端只用它做分组）。"""
    if not device_id:
        return "unknown"
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:DEVICE_HASH_LENGTH]


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def crop_relative_path(owner_id: str, digest: str) -> str:
    return f"contributions/{owner_id}/crop/{digest[:SHA_PREFIX_LENGTH]}.jpg"


def full_relative_path(owner_id: str, digest: str) -> str:
    return f"contributions/{owner_id}/full/{digest[:SHA_PREFIX_LENGTH]}.jpg"


def export_relative_path(filename: str) -> str:
    return f"exports/{filename}"


def export_filename(now: datetime) -> str:
    stamp = now.astimezone().strftime("%Y%m%dT%H%M%S")
    return f"contribution-{stamp}-{secrets.token_hex(3)}.zip"


@dataclass(frozen=True, slots=True)
class RemotePaths:
    """一次样本在收件箱里的三个位置。"""

    crop: str
    meta: str
    full: str | None = None


def remote_paths(
    *, owner_hash: str, local_date: date, digest: str, include_full: bool
) -> RemotePaths:
    base = f"{owner_hash}/{local_date.isoformat()}/{digest[:SHA_PREFIX_LENGTH]}"
    return RemotePaths(
        crop=f"{base}.jpg",
        meta=f"{base}.json",
        full=f"{base}.full.jpg" if include_full else None,
    )


def meta_path_for(remote_crop_path: str) -> str:
    """`.json` 与 `.jpg` 是成对写入的，撤回时要按同一套规则还原元数据路径。"""
    stem, sep, _suffix = remote_crop_path.rpartition(".")
    return f"{stem}.json" if sep else f"{remote_crop_path}.json"


def meta_payload(
    *,
    digest: str,
    state: str,
    confidence: float | None,
    local_date: date,
    include_full: bool,
    width: int,
    height: int,
) -> dict[str, object]:
    """远端元数据：只包含 `META_FIELDS` 里的字段。"""
    return {
        "sha12": digest[:SHA_PREFIX_LENGTH],
        "state": state,
        "confidence": confidence,
        "local_date": local_date.isoformat(),
        "has_full": include_full,
        "width": width,
        "height": height,
    }


def encode_frame(frame: ImageFrame, *, quality: int) -> bytes:
    """重新编码成 JPEG：既控制体积，也顺带丢掉原始元数据（EXIF/GPS）。"""
    bgr = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2BGR)
    ok, buffer = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:  # pragma: no cover - cv2 极少数情况下才会失败
        raise ValueError("图片编码失败")
    return bytes(buffer.tobytes())


# —— 上传载荷 ————————————————————————————————————————————————


@dataclass(frozen=True, slots=True)
class UploadItem:
    """要写进收件箱的一个文件。"""

    remote_path: str
    payload: bytes
    meta: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class UploadBatchResult:
    """一批上传的结果；`failed` 里是失败文件的远端路径。"""

    uploaded: int = 0
    failed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UploadSummary:
    """一次 `upload_pending()` 的汇总。"""

    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    failed_paths: tuple[str, ...] = ()


# —— 数据类 ————————————————————————————————————————————————


@dataclass(frozen=True, slots=True)
class ContributionSetting:
    owner_id: str
    enabled: bool
    include_full: bool
    created_at_utc: datetime
    updated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ContributionSample:
    id: str
    owner_id: str
    device_id: str
    pet_id: str | None
    source_image_id: str
    state: str
    confidence: float | None
    local_date: date
    crop_rel_path: str
    full_rel_path: str | None
    sha256: str
    upload_status: str
    upload_attempts: int
    remote_crop_path: str | None
    remote_full_path: str | None
    uploaded_at_utc: datetime | None
    created_at_utc: datetime

    def __post_init__(self) -> None:
        if self.upload_status not in SAMPLE_STATUSES:
            raise ValueError(f"未知的上传状态: {self.upload_status}")
        if self.upload_attempts < 0:
            raise ValueError("上传次数不能为负")

    @property
    def has_full(self) -> bool:
        return self.full_rel_path is not None


@dataclass(frozen=True, slots=True)
class ContributionExport:
    id: str
    owner_id: str
    filename: str
    rel_path: str
    sample_count: int
    byte_size: int
    created_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ContributionStats:
    """「我的分享」页顶部那几个数字。"""

    total: int = 0
    pending: int = 0
    uploaded: int = 0
    failed: int = 0
    withdrawn: int = 0


@dataclass(frozen=True, slots=True)
class UploadTarget:
    """一个拥有者的待上传样本；`items` 与 `samples` 一一对应（同一顺序）。"""

    owner_id: str
    samples: Sequence[ContributionSample] = field(default_factory=tuple)


__all__ = [
    "CROP_JPEG_QUALITY",
    "DEFAULT_CONTRIBUTION_ENABLED",
    "DEFAULT_CROP_PADDING",
    "DEFAULT_INCLUDE_FULL",
    "DEFAULT_MAX_PENDING",
    "DEFAULT_PER_EVENT_LIMIT",
    "FULL_JPEG_QUALITY",
    "MAX_PER_EVENT_LIMIT",
    "MAX_UPLOAD_ATTEMPTS",
    "META_FIELDS",
    "RETRYABLE_STATUSES",
    "SAMPLE_FAILED",
    "SAMPLE_PENDING",
    "SAMPLE_STATUSES",
    "SAMPLE_UPLOADED",
    "SAMPLE_WITHDRAWN",
    "ContributionExport",
    "ContributionSample",
    "ContributionSetting",
    "ContributionStats",
    "RemotePaths",
    "UploadBatchResult",
    "UploadItem",
    "UploadSummary",
    "UploadTarget",
    "content_hash",
    "crop_relative_path",
    "device_hash",
    "encode_frame",
    "export_filename",
    "export_relative_path",
    "full_relative_path",
    "meta_path_for",
    "meta_payload",
    "remote_paths",
]

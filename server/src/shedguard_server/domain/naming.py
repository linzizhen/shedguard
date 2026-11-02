"""存储路径与内容哈希：路径完全由服务端生成。"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

IMAGES_PREFIX = "images"


def sha256_hex(payload: bytes) -> str:
    """返回小写十六进制摘要，作为幂等键。"""
    return hashlib.sha256(payload).hexdigest()


def build_filename(local_moment: datetime, sha256: str, extension: str) -> str:
    """`HHMMSS_<sha256 前 8 位>.<扩展名>`，时间用设备本地时区。"""
    return f"{local_moment:%H%M%S}_{sha256[:8]}.{extension}"


def build_rel_path(local_date: date, device_id: str, filename: str) -> str:
    """相对数据根目录的路径，统一用 `/` 分隔。"""
    return f"{IMAGES_PREFIX}/{local_date.isoformat()}/{device_id}/{filename}"
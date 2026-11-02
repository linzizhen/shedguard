"""纯函数校验：魔数、设备标识与载荷大小。不触碰 IO。"""

from __future__ import annotations

import re

from shedguard_server.errors import (
    EmptyPayloadError,
    InvalidRequestError,
    PayloadTooLargeError,
)

DEFAULT_DEVICE_ID = "unknown"

_DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sniff_image_extension(data: bytes) -> str | None:
    """按文件头判断真实图片类型，返回扩展名；无法识别时返回 None。"""
    if data.startswith(_JPEG_MAGIC):
        return "jpg"
    if data.startswith(_PNG_MAGIC):
        return "png"
    return None


def validate_device_id(raw: str | None) -> str:
    """校验设备标识，防止路径穿越；缺省为 `unknown`。"""
    if raw is None:
        return DEFAULT_DEVICE_ID
    if not _DEVICE_ID_PATTERN.fullmatch(raw):
        msg = "X-Device-Id 只能包含字母、数字、下划线与连字符，长度 1–64"
        raise InvalidRequestError(msg)
    return raw


def validate_payload_size(byte_size: int, limit: int) -> None:
    """空载荷与超限载荷在读取阶段即拒绝。"""
    if byte_size <= 0:
        raise EmptyPayloadError("请求体为空")
    if byte_size > limit:
        raise PayloadTooLargeError(f"图片超过上限 {limit} 字节")
"""图像解码。"""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np

from shedguard_server.domain.imaging import ImageFrame, Uint8Image
from shedguard_server.errors import UnsupportedMediaTypeError


def decode_image(payload: bytes) -> ImageFrame:
    """把 JPEG 或 PNG 字节解成 RGB 帧。"""
    buffer = np.frombuffer(payload, dtype=np.uint8)
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise UnsupportedMediaTypeError("无法解码图片")
    rgb = cast(Uint8Image, cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))
    height, width = rgb.shape[:2]
    return ImageFrame(width=int(width), height=int(height), rgb=rgb)
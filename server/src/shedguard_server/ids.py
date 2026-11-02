"""标识生成。"""

from __future__ import annotations

import os
import time

# Crockford Base32：去掉 I、L、O、U，避免肉眼混淆。
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LENGTH = 26


def new_request_id() -> str:
    """生成 ULID 风格标识：48 位毫秒时间戳 + 80 位随机，共 130 位编码为 26 字符。

    同毫秒内生成的标识按随机部分排序，跨毫秒严格递增，便于日志按字典序排列。
    """
    timestamp_ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    value = (timestamp_ms << 80) | randomness

    chars: list[str] = []
    for _ in range(_LENGTH):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))
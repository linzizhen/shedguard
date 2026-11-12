"""令牌的生成与摘要。

服务端从不保存令牌明文；只保存 sha256 十六进制摘要，比对时用摘要。
"""

from __future__ import annotations

import hashlib
import secrets

# 32 字节随机数据，token_urlsafe 后约 43 个字符。
TOKEN_BYTES = 32


def new_token() -> str:
    """生成一个新的令牌明文，只在注册响应里返回一次。"""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw: str) -> str:
    """令牌摘要；空串或空白串会得到空摘要，避免与有效令牌冲突。"""
    if not raw.strip():
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

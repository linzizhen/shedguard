"""摄像头凭据的加解密。

只做一件事：把「不能明文落库的字段」加密成一个字符串，需要时再解回来。
密钥来自 `SHEDGUARD_SECRET_KEY`（Fernet key）。没配密钥时，写操作必须失败而不是明文落库。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Protocol

from cryptography.fernet import Fernet, InvalidToken

SECRET_KEY_BYTES: Final = 32
EMPTY_SECRET_MESSAGE: Final = "服务器还没配置密钥，暂时不能保存摄像头密码"


class SecretBoxError(Exception):
    """加解密相关的错误，`str(exc)` 可直接给用户看。"""


class SecretBoxLike(Protocol):
    @property
    def configured(self) -> bool: ...

    def encrypt(self, values: dict[str, str]) -> str: ...

    def decrypt(self, token: str) -> dict[str, str]: ...


@dataclass(frozen=True, slots=True)
class SecretBox:
    """配置了密钥时的实现。"""

    fernet: Fernet

    @property
    def configured(self) -> bool:
        return True

    def encrypt(self, values: dict[str, str]) -> str:
        if not values:
            return ""
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self.fernet.encrypt(payload).decode("ascii")

    def decrypt(self, token: str) -> dict[str, str]:
        if not token:
            return {}
        try:
            raw = self.fernet.decrypt(token.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            raise SecretBoxError("保存的摄像头密码解不开，可能换过密钥，请重新填一次") from exc
        try:
            values = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecretBoxError("保存的摄像头密码已损坏，请重新填一次") from exc
        if not isinstance(values, dict):
            raise SecretBoxError("保存的摄像头密码格式不对，请重新填一次")
        return {str(key): str(value) for key, value in values.items()}


@dataclass(frozen=True, slots=True)
class NullSecretBox:
    """没配密钥时的实现：读可以，写必须显式失败。"""

    @property
    def configured(self) -> bool:
        return False

    def encrypt(self, values: dict[str, str]) -> str:
        raise SecretBoxError(EMPTY_SECRET_MESSAGE)

    def decrypt(self, token: str) -> dict[str, str]:
        if token:
            raise SecretBoxError(EMPTY_SECRET_MESSAGE)
        return {}


def build_secret_box(key: str) -> SecretBox | NullSecretBox:
    """空 key → 空实现；格式不对 → 直接抛错（启动即校验，不让问题拖到运行期）。"""
    cleaned = key.strip()
    if not cleaned:
        return NullSecretBox()
    try:
        fernet = Fernet(cleaned.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SecretBoxError("SHEDGUARD_SECRET_KEY 不是合法的 Fernet 密钥（44 位 base64）") from exc
    return SecretBox(fernet)


def generate_key() -> str:
    """生成一把新密钥，供部署时用。"""
    return Fernet.generate_key().decode("ascii")


__all__ = [
    "EMPTY_SECRET_MESSAGE",
    "SECRET_KEY_BYTES",
    "NullSecretBox",
    "SecretBox",
    "SecretBoxError",
    "SecretBoxLike",
    "build_secret_box",
    "generate_key",
]
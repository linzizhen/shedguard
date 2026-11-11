"""推送网关的领域契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class PushStatus(StrEnum):
    """单条推送的投递结果。"""

    SENT = "sent"
    INVALID = "invalid"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PushMessage:
    """一条待推送的通知。`to` 是 Expo 推送 token。"""

    to: str
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PushOutcome:
    status: PushStatus
    detail: str | None = None


class PushGateway(Protocol):
    """推送通道抽象；实现方负责与具体厂商交互。"""

    def send(self, message: PushMessage) -> PushOutcome:
        """投递一条通知，返回投递结果。"""
        ...

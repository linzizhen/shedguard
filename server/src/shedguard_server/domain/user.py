"""用户领域对象：匿名设备账号。

设计要点：没有登录流程，App 首次启动时向服务端换取一个 token，
服务端只保存 token 的 sha256 摘要，明文只在注册响应里出现一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    """一个匿名账号；`id` 是稳定的用户标识，用于资源归属。"""

    id: str
    created_at_utc: datetime
    last_seen_at_utc: datetime | None = None

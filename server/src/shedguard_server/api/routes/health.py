"""健康检查：存活探针恒 200，就绪探针在依赖不可用时 503。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request

from shedguard_server.config import Settings
from shedguard_server.errors import StorageUnavailableError

router = APIRouter(tags=["health"])


def _data_dir_ready(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """进程存活即返回；不检查任何外部依赖。"""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    """依赖就绪才返回 200，否则抛 503 交给统一错误处理器。"""
    settings: Settings = request.app.state.settings
    if not _data_dir_ready(settings.data_dir):
        raise StorageUnavailableError(f"数据目录不可用: {settings.data_dir}")
    return {"status": "ready"}
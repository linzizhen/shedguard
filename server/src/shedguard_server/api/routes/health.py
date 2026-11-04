"""健康检查：存活探针恒 200，就绪探针在依赖不可用时 503。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from shedguard_server.config import Settings
from shedguard_server.errors import ModelUnavailableError, StorageUnavailableError

router = APIRouter(tags=["health"])


def _data_dir_ready(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _database_ready(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


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
    if getattr(request.app.state, "migration_error", None) is not None:
        raise StorageUnavailableError("数据库迁移未完成")
    detector_error = getattr(request.app.state, "detector_error", None)
    if detector_error is not None:
        raise StorageUnavailableError("检测模型加载失败")
    classifier_error = getattr(request.app.state, "classifier_error", None)
    if classifier_error is not None:
        raise ModelUnavailableError("状态分类模型加载失败")
    engine: Engine = request.app.state.engine
    if not _database_ready(engine):
        raise StorageUnavailableError("数据库不可用")
    return {"status": "ready"}
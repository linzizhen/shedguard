"""HTTP 层共享依赖：配置、数据库会话、仓储与存储。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.infra.repository import ImageRepository
from shedguard_server.infra.storage import LocalStorage


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_image_repository(session: Annotated[Session, Depends(get_session)]) -> ImageRepository:
    return ImageRepository(session)


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> LocalStorage:
    return LocalStorage(settings.data_dir)
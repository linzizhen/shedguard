"""集成测试共享 fixture：用临时数据目录与临时数据库装配应用。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from shedguard_server.app import create_app
from shedguard_server.config import Settings


@pytest.fixture()
def settings(workdir: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=workdir / "data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        max_upload_bytes=1024,
        auth_enabled=False,
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    engine: Engine = app.state.engine
    engine.dispose()
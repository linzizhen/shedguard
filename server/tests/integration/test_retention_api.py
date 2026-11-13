"""照片保留策略的接口级验证：清理后文件与元数据都消失，关闭时保持原样。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.retention import purge_once


def _jpeg(tag: int) -> bytes:
    """同一批测试里要区分多张图，避免按 sha256 被判为重复上传。"""
    return b"\xff\xd8\xff" + bytes([tag]) + b"\x00" * 27 + b"\xff\xd9"


def _upload(
    client: TestClient,
    *,
    captured_at: datetime,
    tag: int,
    filename: str,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/images",
        files={"file": (filename, _jpeg(tag), "image/jpeg")},
        headers={
            "X-Captured-At": captured_at.isoformat().replace("+00:00", "Z"),
            "X-Device-Id": "cam-retention",
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, str] = response.json()
    return body


def _purge(client: TestClient, settings: Settings, *, now: datetime, days: int) -> int:
    enabled = settings.model_copy(update={"image_retention_days": days})
    app = cast(FastAPI, client.app)
    return purge_once(
        session_factory=app.state.session_factory,
        settings=enabled,
        storage=LocalStorage(settings.data_dir),
        now=now,
    )


def test_purge_removes_expired_image_file_and_row(
    client: TestClient, settings: Settings
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    expired = _upload(
        client,
        captured_at=now - timedelta(days=10),
        tag=1,
        filename="expired.jpg",
    )
    fresh = _upload(client, captured_at=now, tag=2, filename="fresh.jpg")
    storage = LocalStorage(settings.data_dir)
    assert storage.exists(expired["rel_path"])

    removed = _purge(client, settings, now=now, days=7)

    assert removed == 1
    assert not storage.exists(expired["rel_path"])
    assert client.get(f"/api/v1/images/{expired['id']}").status_code == 404
    assert storage.exists(fresh["rel_path"])
    assert client.get(f"/api/v1/images/{fresh['id']}").status_code == 200


def test_unexpired_image_survives_purge(client: TestClient, settings: Settings) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    fresh = _upload(
        client,
        captured_at=now - timedelta(days=1),
        tag=3,
        filename="recent.jpg",
    )

    removed = _purge(client, settings, now=now, days=7)

    assert removed == 0
    assert LocalStorage(settings.data_dir).exists(fresh["rel_path"])
    assert client.get(f"/api/v1/images/{fresh['id']}").status_code == 200


def test_missing_file_does_not_break_purge(client: TestClient, settings: Settings) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    expired = _upload(
        client,
        captured_at=now - timedelta(days=30),
        tag=4,
        filename="lost.jpg",
    )
    LocalStorage(settings.data_dir).remove(expired["rel_path"])
    assert not LocalStorage(settings.data_dir).exists(expired["rel_path"])

    removed = _purge(client, settings, now=now, days=7)

    assert removed == 1
    assert client.get(f"/api/v1/images/{expired['id']}").status_code == 404


def test_disabled_retention_keeps_everything(client: TestClient, settings: Settings) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    expired = _upload(
        client,
        captured_at=now - timedelta(days=30),
        tag=5,
        filename="kept.jpg",
    )

    removed = _purge(client, settings, now=now, days=0)

    assert removed == 0
    assert LocalStorage(settings.data_dir).exists(expired["rel_path"])
    assert client.get(f"/api/v1/images/{expired['id']}").status_code == 200


def test_lifespan_starts_retention_task_only_when_enabled(workdir: Path) -> None:
    base = Settings(  # type: ignore[call-arg]
        _env_file=None,
        data_dir=workdir / "lifespan-data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        auth_enabled=False,
        health_monitor_enabled=False,
        image_retention_days=1,
    )
    app = create_app(base)
    with TestClient(app):
        assert app.state.retention_task is not None
    engine: Engine = app.state.engine
    engine.dispose()

    disabled = base.model_copy(update={"image_retention_days": 0})
    app_disabled = create_app(disabled)
    with TestClient(app_disabled):
        assert app_disabled.state.retention_task is None
    engine_disabled: Engine = app_disabled.state.engine
    engine_disabled.dispose()
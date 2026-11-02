"""HTTP 骨架：健康检查、请求 ID 与统一错误响应。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.infra.db import create_db_engine


def _client(workdir: Path) -> TestClient:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]
    return TestClient(create_app(settings))


def test_healthz_returns_ok(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_ok_when_data_dir_writable(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readyz_reports_503_when_data_dir_missing(workdir: Path) -> None:
    missing = workdir / "nope"
    settings = Settings(_env_file=None, data_dir=missing)  # type: ignore[call-arg]

    with TestClient(create_app(settings, create_data_dir=False)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"


def test_unknown_path_uses_error_envelope(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == response.headers["X-Request-Id"]


def test_request_id_is_generated_when_absent(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/healthz")

    request_id = response.headers["X-Request-Id"]
    assert len(request_id) == 26
    assert set(request_id) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_client_request_id_is_echoed(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/healthz", headers={"X-Request-Id": "client-supplied"})

    assert response.headers["X-Request-Id"] == "client-supplied"


def test_readyz_reports_503_when_migration_failed(
    workdir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_: str) -> None:
        msg = "迁移故意失败"
        raise RuntimeError(msg)

    monkeypatch.setattr("shedguard_server.app.run_migrations", boom)
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"


def test_readyz_reports_503_when_database_unreachable(workdir: Path) -> None:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    with TestClient(create_app(settings)) as client:
        client.app.state.engine = create_db_engine(  # type: ignore[attr-defined]
            f"sqlite:///{(workdir / 'missing-dir' / 'x.db').as_posix()}"
        )
        response = client.get("/readyz")

    assert response.status_code == 503
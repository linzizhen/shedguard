"""HTTP 骨架：健康检查、请求 ID 与统一错误响应。"""

from pathlib import Path

from fastapi.testclient import TestClient

from shedguard_server.app import create_app
from shedguard_server.config import Settings


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
    assert len(request_id) == 32
    int(request_id, 16)  # 必须是十六进制


def test_client_request_id_is_echoed(workdir: Path) -> None:
    with _client(workdir) as client:
        response = client.get("/healthz", headers={"X-Request-Id": "client-supplied"})

    assert response.headers["X-Request-Id"] == "client-supplied"
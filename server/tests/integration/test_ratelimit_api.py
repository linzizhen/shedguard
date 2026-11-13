"""接口级验证：限流开启返回 429、关闭不限流、健康检查与文档始终放行。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from shedguard_server.app import create_app
from shedguard_server.config import Settings

IMAGES = "/api/v1/images"
LIMITED_EXEMPT = ("/healthz", "/readyz", "/docs", "/openapi.json")


@pytest.fixture()
def limited(workdir: Path) -> Iterator[tuple[TestClient, Settings]]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        data_dir=workdir / "limited-data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        max_upload_bytes=1024,
        auth_enabled=False,
        health_monitor_enabled=False,
        rate_limit_per_minute=2,
        rate_limit_burst=2,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, settings
    engine: Engine = app.state.engine
    engine.dispose()


def test_exceeding_limit_returns_429(limited: tuple[TestClient, Settings]) -> None:
    client, _ = limited
    assert client.get(IMAGES).status_code == 200
    assert client.get(IMAGES).status_code == 200

    response = client.get(IMAGES)

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["message"] == "请求过于频繁，请稍后再试"
    assert body["error"]["request_id"]
    assert response.headers["X-Request-Id"] == body["error"]["request_id"]


def test_disabled_limit_never_blocks(client: TestClient) -> None:
    for _ in range(10):
        assert client.get(IMAGES).status_code == 200


def test_exempt_paths_are_always_allowed(limited: tuple[TestClient, Settings]) -> None:
    client, _ = limited
    for path in LIMITED_EXEMPT:
        for _ in range(5):
            assert client.get(path).status_code == 200


def test_limits_are_per_authorization_token(limited: tuple[TestClient, Settings]) -> None:
    client, _ = limited
    token_a = {"Authorization": "Bearer token-a"}
    token_b = {"Authorization": "Bearer token-b"}

    assert client.get(IMAGES, headers=token_a).status_code == 200
    assert client.get(IMAGES, headers=token_a).status_code == 200
    assert client.get(IMAGES, headers=token_a).status_code == 429
    assert client.get(IMAGES, headers=token_b).status_code == 200
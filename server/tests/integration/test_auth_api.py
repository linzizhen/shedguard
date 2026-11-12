"""匿名账号鉴权与多用户隔离的集成测试。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from shedguard_server.app import create_app
from shedguard_server.config import Settings


def _settings(workdir: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "data_dir": workdir / "data",
        "db_url": None,
        "timezone": "Asia/Shanghai",
        "log_level": "INFO",
        "log_format": "json",
        "max_upload_bytes": 1024,
        "auth_enabled": True,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


@pytest.fixture()
def auth_client(workdir: Path) -> Iterator[TestClient]:
    app = create_app(_settings(workdir))
    with TestClient(app) as test_client:
        yield test_client
    engine: Engine = app.state.engine
    engine.dispose()


def _register(client: TestClient) -> str:
    response = client.post("/api/v1/users/anonymous")
    assert response.status_code == 201
    return str(response.json()["token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAnonymousAccount:
    def test_register_returns_token_and_user_id(self, auth_client: TestClient) -> None:
        response = auth_client.post("/api/v1/users/anonymous")
        assert response.status_code == 201
        body = response.json()
        assert body["token"]
        assert body["user_id"]

    def test_me_without_token_is_401(self, auth_client: TestClient) -> None:
        response = auth_client.get("/api/v1/users/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    def test_me_with_bad_token_is_401(self, auth_client: TestClient) -> None:
        response = auth_client.get("/api/v1/users/me", headers=_auth("bogus"))
        assert response.status_code == 401

    def test_me_with_token_returns_same_user(self, auth_client: TestClient) -> None:
        token = _register(auth_client)
        response = auth_client.get("/api/v1/users/me", headers=_auth(token))
        assert response.status_code == 200
        assert response.json()["user_id"]


class TestPetIsolation:
    def test_pets_require_auth(self, auth_client: TestClient) -> None:
        assert auth_client.get("/api/v1/pets").status_code == 401
        assert (
            auth_client.post("/api/v1/pets", json={"name": "小橙"}).status_code == 401
        )

    def test_two_users_cannot_see_each_other(self, auth_client: TestClient) -> None:
        token_a = _register(auth_client)
        token_b = _register(auth_client)
        created = auth_client.post(
            "/api/v1/pets", json={"name": "小橙"}, headers=_auth(token_a)
        )
        assert created.status_code == 201
        pet_id = created.json()["id"]

        assert auth_client.get("/api/v1/pets", headers=_auth(token_a)).json()["items"]
        assert auth_client.get("/api/v1/pets", headers=_auth(token_b)).json()["items"] == []
        # 别人的宠物按不存在处理，返回 404 而不是 403。
        assert (
            auth_client.get(f"/api/v1/pets/{pet_id}", headers=_auth(token_b)).status_code
            == 404
        )


class TestDeviceToken:
    def test_upload_rejects_wrong_device_token(self, workdir: Path) -> None:
        app = create_app(_settings(workdir, device_token="secret-token"))
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/images",
                content=b"\xff\xd8\xff\xd9",
                headers={
                    "content-type": "image/jpeg",
                    "x-device-id": "gecko-eye-01",
                    "x-device-token": "wrong",
                },
            )
            assert response.status_code == 401
        app.state.engine.dispose()

    def test_upload_accepts_matching_device_token(self, workdir: Path) -> None:
        app = create_app(_settings(workdir, device_token="secret-token"))
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/images",
                content=b"\xff\xd8\xff\xd9",
                headers={
                    "content-type": "image/jpeg",
                    "x-device-id": "gecko-eye-01",
                    "x-device-token": "secret-token",
                },
            )
            assert response.status_code == 201
        app.state.engine.dispose()

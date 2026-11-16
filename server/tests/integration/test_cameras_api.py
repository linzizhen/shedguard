"""摄像头接入的集成测试：注册、测试连接、抓拍入库、失败兜底。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import shedguard_server.services.cameras as cameras_service
from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.domain.camera import CameraError
from shedguard_server.infra.crypto import generate_key
from shedguard_server.infra.push import SkippedPushGateway
from shedguard_server.infra.storage import LocalStorage


def _settings(workdir: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "data_dir": workdir / "data",
        "db_url": None,
        "timezone": "Asia/Shanghai",
        "log_level": "INFO",
        "log_format": "json",
        "max_upload_bytes": 400_000,
        "auth_enabled": False,
        "health_monitor_enabled": False,
        "portrait_enabled": False,
        "contribution_enabled": False,
        "camera_enabled": False,
        "secret_key": generate_key(),
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg,arg-type]


@pytest.fixture()
def client(workdir: Path) -> Iterator[TestClient]:
    app = create_app(_settings(workdir))
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


def _jpeg(width: int = 160, height: int = 120) -> bytes:
    pixels = np.full((height, width, 3), 90, dtype=np.uint8)
    pixels[30:90, 40:120] = 140
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.tobytes()


class _FakeSource:
    name = "fake"

    def __init__(self, payload: bytes | None = None, error: CameraError | None = None) -> None:
        self.payload = payload or _jpeg()
        self.error = error

    def fetch_frame(self) -> bytes:
        if self.error is not None:
            raise self.error
        return self.payload


def _use_source(monkeypatch: pytest.MonkeyPatch, source: _FakeSource) -> None:
    monkeypatch.setattr(cameras_service, "build_camera_source", lambda *a, **k: source)


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "rtsp",
        "label": "客厅的摄像头",
        "config": {"url": "rtsp://192.168.1.9/stream", "user": "admin", "credential": "p@ss"},
    }
    body.update(overrides)
    response = client.post("/api/v1/cameras", json=body)
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


class TestCreateAndList:
    def test_create_hides_secret(self, client: TestClient) -> None:
        created = _create(client)
        assert created["has_secret"] is True
        # 凭据单独加密，公开配置里只剩不带账号的地址
        assert created["config"] == {"url": "rtsp://192.168.1.9/stream"}
        assert "credential" not in created["config"]
        assert created["status"] == "never_tested"

    def test_create_without_secret_key_is_rejected(self, workdir: Path) -> None:
        app = create_app(_settings(workdir, secret_key=""))
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/cameras",
                json={
                    "provider": "rtsp",
                    "label": "客厅",
                    "config": {"url": "rtsp://x/1", "credential": "p"},
                },
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "INVALID_REQUEST"
        app.state.engine.dispose()

    def test_list_and_patch(self, client: TestClient) -> None:
        created = _create(client)
        listed = client.get("/api/v1/cameras")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

        patched = client.patch(
            f"/api/v1/cameras/{created['id']}",
            json={"label": "小箱", "enabled": False},
        )
        assert patched.status_code == 200
        assert patched.json()["label"] == "小箱"
        assert patched.json()["enabled"] is False

    def test_unknown_camera_is_404(self, client: TestClient) -> None:
        assert client.patch("/api/v1/cameras/nope", json={"label": "x"}).status_code == 404
        assert client.delete("/api/v1/cameras/nope").status_code == 404


class TestTestConnection:
    def test_ok(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_source(monkeypatch, _FakeSource())
        created = _create(client)
        result = client.post(f"/api/v1/cameras/{created['id']}/test")
        assert result.status_code == 200
        assert result.json()["ok"] is True
        camera = client.get("/api/v1/cameras").json()["items"][0]
        assert camera["status"] == "ok"
        assert camera["consecutive_failures"] == 0

    def test_failure_records_status(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_source(
            monkeypatch,
            _FakeSource(error=CameraError("auth_failed", "应用密钥不对")),
        )
        created = _create(client)
        result = client.post(f"/api/v1/cameras/{created['id']}/test")
        assert result.status_code == 200
        assert result.json()["ok"] is False
        assert result.json()["kind"] == "auth_failed"
        camera = client.get("/api/v1/cameras").json()["items"][0]
        assert camera["status"] == "auth_failed"
        assert camera["consecutive_failures"] == 1


class TestSnapshot:
    def test_snapshot_ingests_image(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_source(monkeypatch, _FakeSource())
        created = _create(client)
        response = client.post(f"/api/v1/cameras/{created['id']}/snapshot")
        assert response.status_code == 202
        body = response.json()
        assert body["device_id"] == f"camera-{created['id']}"
        assert body["duplicate"] is False

        images = client.get(f"/api/v1/images?device_id=camera-{created['id']}")
        assert images.status_code == 200
        assert images.json()["total"] == 1

    def test_snapshot_failure_is_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_source(monkeypatch, _FakeSource(error=CameraError("unreachable", "连不上")))
        created = _create(client)
        response = client.post(f"/api/v1/cameras/{created['id']}/snapshot")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "CAMERA_UNAVAILABLE"

    def test_delete(self, client: TestClient) -> None:
        created = _create(client)
        assert client.delete(f"/api/v1/cameras/{created['id']}").status_code == 204
        assert client.get("/api/v1/cameras").json()["items"] == []


class TestPoll:
    def test_poll_counts_new_frames(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_source(monkeypatch, _FakeSource())
        created = _create(client)
        state = client.app.state  # type: ignore[attr-defined]
        settings = state.settings.model_copy(
            update={"camera_enabled": True, "camera_max_failures": 3}
        )
        counted = cameras_service.poll_once(
            session_factory=state.session_factory,
            settings=settings,
            storage=LocalStorage(settings.data_dir),
            gateway=SkippedPushGateway(),
            now=datetime(2026, 11, 16, 4, 0, tzinfo=UTC),
        )
        assert counted == 1
        # 同一帧再抓一次会被 sha256 去重，不重复计数
        again = cameras_service.poll_once(
            session_factory=state.session_factory,
            settings=settings,
            storage=LocalStorage(settings.data_dir),
            gateway=SkippedPushGateway(),
            now=datetime(2026, 11, 16, 4, 30, tzinfo=UTC),
        )
        assert again == 0
        assert created["id"]

    def test_poll_creates_offline_alert_once(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use_source(monkeypatch, _FakeSource(error=CameraError("unreachable", "连不上")))
        _create(client)
        state = client.app.state  # type: ignore[attr-defined]
        settings = state.settings.model_copy(
            update={"camera_enabled": True, "camera_max_failures": 1}
        )
        state = client.app.state  # type: ignore[attr-defined]
        kwargs = {
            "session_factory": state.session_factory,
            "settings": settings,
            "storage": LocalStorage(settings.data_dir),
            "gateway": SkippedPushGateway(),
        }
        cameras_service.poll_once(**kwargs, now=datetime(2026, 11, 16, 4, 0, tzinfo=UTC))
        cameras_service.poll_once(**kwargs, now=datetime(2026, 11, 16, 4, 30, tzinfo=UTC))

        alerts = client.get("/api/v1/alerts").json()["items"]
        offline = [item for item in alerts if item["kind"] == "camera_offline"]
        assert len(offline) == 1

    def test_poll_is_skipped_when_disabled(self, client: TestClient) -> None:
        state = client.app.state  # type: ignore[attr-defined]
        settings = state.settings
        assert (
            cameras_service.poll_once(
                session_factory=state.session_factory,
                settings=settings,
                storage=LocalStorage(settings.data_dir),
                gateway=SkippedPushGateway(),
            )
            == 0
        )
        assert getattr(state, "camera_task", None) is None

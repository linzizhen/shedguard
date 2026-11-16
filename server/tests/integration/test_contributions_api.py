"""数据贡献（自愿分享）的集成测试。"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction

DEVICE = "dev-1"


def _settings(workdir: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=workdir / "data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        max_upload_bytes=400_000,
        auth_enabled=False,
        health_monitor_enabled=False,
        portrait_enabled=False,
        contribution_enabled=False,
    )


@pytest.fixture()
def client(workdir: Path) -> Iterator[TestClient]:
    app = create_app(_settings(workdir))
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


def make_jpeg(*, brightness: int = 120, size: int = 96) -> bytes:
    pixels = np.full((size, size, 3), brightness, dtype=np.uint8)
    pixels[size // 4 : size // 2, size // 4 : size // 2] = 160
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


class _FixedDetector:
    name = "fixed"

    def detect(self, frame: ImageFrame) -> Detection:
        return Detection(
            x1=int(frame.width * 0.15),
            y1=int(frame.height * 0.15),
            x2=int(frame.width * 0.85),
            y2=int(frame.height * 0.85),
            confidence=0.9,
        )


class _FakeClassifier:
    name = "fake-state-classifier"

    def classify(self, frame: ImageFrame) -> StatePrediction:
        confidence = 0.9
        others = (1.0 - confidence) / 2.0
        return StatePrediction(
            state=ShedState.SHEDDING,
            confidence=confidence,
            probabilities={"normal": others, "opaque": others, "shedding": confidence},
        )


def _prepare(client: TestClient) -> str:
    """装好假检测器/分类器，建宠物并绑定设备，返回 pet_id。"""
    state = client.app.state  # type: ignore[attr-defined]
    state.detector = _FixedDetector()
    state.state_classifier = _FakeClassifier()
    pet_id = str(client.post("/api/v1/pets", json={"name": "小橘子"}).json()["id"])
    client.post(
        "/api/v1/devices",
        json={
            "expo_push_token": "",
            "platform": "android",
            "device_id": DEVICE,
            "pet_id": pet_id,
        },
    )
    return pet_id


def _upload(client: TestClient, payload: bytes) -> str:
    response = cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", payload, "image/jpeg")},
            headers={"X-Device-Id": DEVICE},
        ),
    )
    assert response.status_code in {200, 201}
    return str(response.json()["id"])


def _enable(client: TestClient, *, include_full: bool = False) -> None:
    response = client.put(
        "/api/v1/contribution-settings",
        json={"enabled": True, "include_full": include_full},
    )
    assert response.status_code == 200


def _sample_files(client: TestClient) -> list[Path]:
    root = client.app.state.settings.data_dir / "contributions"  # type: ignore[attr-defined]
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


class TestSettings:
    def test_defaults_to_off(self, client: TestClient) -> None:
        body = client.get("/api/v1/contribution-settings").json()

        assert body["enabled"] is False
        assert body["include_full"] is False

    def test_update_persists(self, client: TestClient) -> None:
        _enable(client, include_full=True)

        body = client.get("/api/v1/contribution-settings").json()
        assert body["enabled"] is True
        assert body["include_full"] is True


class TestEnqueue:
    def test_switch_off_keeps_nothing(self, client: TestClient) -> None:
        _prepare(client)
        _upload(client, make_jpeg(brightness=100))

        body = client.get("/api/v1/contributions").json()
        assert body["items"] == []
        assert body["stats"]["total"] == 0
        assert _sample_files(client) == []

    def test_switch_on_writes_crop(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client)
        _upload(client, make_jpeg(brightness=100))

        body = client.get("/api/v1/contributions").json()
        assert len(body["items"]) == 1
        sample = body["items"][0]
        assert sample["upload_status"] == "pending"
        assert sample["state"] == "shedding"
        assert sample["has_full"] is False

        files = _sample_files(client)
        assert len(files) == 1
        assert files[0].suffix == ".jpg"

    def test_full_image_is_kept_when_requested(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client, include_full=True)
        _upload(client, make_jpeg(brightness=110))

        sample = client.get("/api/v1/contributions").json()["items"][0]
        assert sample["has_full"] is True
        assert len(_sample_files(client)) == 2

    def test_caps_samples_per_event(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client)
        for brightness in (90, 100, 110, 120):
            _upload(client, make_jpeg(brightness=brightness, size=96 + brightness % 7))

        body = client.get("/api/v1/contributions").json()
        assert len(body["items"]) == 3
        assert body["stats"]["total"] == 3

    def test_image_endpoint_returns_jpeg(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client)
        _upload(client, make_jpeg(brightness=100))
        sample_id = client.get("/api/v1/contributions").json()["items"][0]["id"]

        response = client.get(f"/api/v1/contributions/{sample_id}/image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:2] == b"\xff\xd8"


class TestWithdraw:
    def test_withdraw_removes_local_file(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client)
        _upload(client, make_jpeg(brightness=100))
        sample_id = client.get("/api/v1/contributions").json()["items"][0]["id"]

        response = client.post(f"/api/v1/contributions/{sample_id}/withdraw")
        assert response.status_code == 200
        assert response.json()["upload_status"] == "withdrawn"
        assert _sample_files(client) == []

    def test_withdraw_unknown_sample(self, client: TestClient) -> None:
        _prepare(client)

        response = client.post("/api/v1/contributions/nope/withdraw")
        assert response.status_code == 404


class TestExport:
    def test_export_then_download(self, client: TestClient) -> None:
        _prepare(client)
        _enable(client)
        _upload(client, make_jpeg(brightness=100))

        created = client.post("/api/v1/contributions/export")
        assert created.status_code == 201
        export = created.json()
        assert export["filename"].startswith("contribution-")
        assert export["sample_count"] == 1

        downloaded = client.get(f"/api/v1/contributions/exports/{export['id']}")
        assert downloaded.status_code == 200
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            names = archive.namelist()
            assert len([name for name in names if name.endswith(".jpg")]) == 1
            assert len([name for name in names if name.endswith(".json")]) == 1

    def test_export_without_samples_is_rejected(self, client: TestClient) -> None:
        _prepare(client)

        response = client.post("/api/v1/contributions/export")
        assert response.status_code == 400


class TestUpload:
    def test_upload_now_without_inbox_skips_and_keeps_pending(
        self, client: TestClient
    ) -> None:
        """没配收件箱时不能假装成功，也不能把样本烧成 failed。"""
        _prepare(client)
        _enable(client)
        _upload(client, make_jpeg(brightness=100))

        response = client.post("/api/v1/contributions/upload-now")
        assert response.status_code == 200
        body = response.json()
        assert body["skipped"] == 1
        assert body["uploaded"] == 0
        assert body["failed"] == 0

        sample = client.get("/api/v1/contributions").json()["items"][0]
        assert sample["upload_status"] == "pending"
        assert sample["upload_attempts"] == 0

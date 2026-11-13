"""萌照生成与接口的集成测试。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.infra.push import SkippedPushGateway
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.portraits import scan_once

TZ = ZoneInfo("Asia/Shanghai")


def _settings(workdir: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=workdir / "data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        max_upload_bytes=200_000,
        auth_enabled=False,
        health_monitor_enabled=False,
        portrait_enabled=False,
    )


@pytest.fixture()
def client(workdir: Path) -> Iterator[TestClient]:
    app = create_app(_settings(workdir))
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


def _photo(width: int = 240, height: int = 180) -> bytes:
    # 中间亮块代表守宫身体，四周压暗：亮度过高会被 high_light_ratio 当反光剔掉，
    # 所以整体都用中间调，避免测试图自己触发选片门槛。
    pixels = np.full((height, width, 3), 70, dtype=np.uint8)
    pixels[40:140, 70:170] = 120
    pixels[60:80, 90:110] = 40
    ok, encoded = cv2.imencode(
        ".jpg", cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 90]
    )
    assert ok
    return encoded.tobytes()


class _FixedDetector:
    """固定框住画面中间一块，模拟「守宫占了画面的一大块」。"""

    name = "fixed"

    def detect(self, frame: ImageFrame) -> Detection:
        return Detection(
            x1=int(frame.width * 0.2),
            y1=int(frame.height * 0.2),
            x2=int(frame.width * 0.8),
            y2=int(frame.height * 0.8),
            confidence=0.9,
        )


def _local_noon() -> datetime:
    return datetime.now(TZ).replace(hour=12, minute=0, second=0, microsecond=0)


def _prepare(client: TestClient, *, pet: bool = True) -> tuple[str | None, str]:
    client.app.state.detector = _FixedDetector()  # type: ignore[attr-defined]
    captured = _local_noon().replace(hour=10).isoformat()
    uploaded = cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", _photo(), "image/jpeg")},
            headers={"X-Device-Id": "dev-1", "X-Captured-At": captured},
        ),
    )
    image_id = uploaded.json()["id"]
    client.post(f"/api/v1/analysis/{image_id}")
    if not pet:
        return None, image_id
    pet_id = client.post("/api/v1/pets", json={"name": "小橘子"}).json()["id"]
    client.post(
        "/api/v1/devices",
        json={
            "expo_push_token": "",
            "platform": "android",
            "device_id": "dev-1",
            "pet_id": pet_id,
        },
    )
    return pet_id, image_id


def _scan(client: TestClient) -> int:
    state = client.app.state  # type: ignore[attr-defined]
    settings = state.settings.model_copy(update={"portrait_enabled": True})
    return scan_once(
        session_factory=state.session_factory,
        settings=settings,
        storage=LocalStorage(settings.data_dir),
        gateway=SkippedPushGateway(),
        now=_local_noon().astimezone(UTC),
    )


class TestGeneration:
    def test_scan_creates_one_shot(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)

        assert _scan(client) == 1

        items = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"]
        assert len(items) == 1
        assert items[0]["width"] == items[0]["height"]
        assert items[0]["slot"] == 0

    def test_second_scan_is_idempotent(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)

        _scan(client)
        assert _scan(client) == 0
        items = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"]
        assert len(items) == 1

    def test_scan_without_pet_does_nothing(self, client: TestClient) -> None:
        _prepare(client, pet=False)

        assert _scan(client) == 0

    def test_scan_reports_alert(self, client: TestClient) -> None:
        _prepare(client)

        _scan(client)

        alerts = client.get("/api/v1/alerts").json()["items"]
        assert [item["kind"] for item in alerts] == ["portrait_ready"]

    def test_generated_image_is_readable(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)
        _scan(client)
        shot_id = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"][0]["id"]

        response = client.get(f"/api/v1/portraits/{shot_id}/image")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert len(response.content) > 200


class TestSettings:
    def test_defaults_when_never_saved(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)

        body = client.get(f"/api/v1/pets/{pet_id}/portrait-settings").json()

        assert body["enabled"] is True
        assert body["per_day"] == 1
        assert body["start_hour"] == 8
        assert body["end_hour"] == 20

    def test_update_persists(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)

        updated = client.put(
            f"/api/v1/pets/{pet_id}/portrait-settings",
            json={"per_day": 3, "start_hour": 9},
        ).json()

        assert updated["per_day"] == 3
        assert updated["start_hour"] == 9
        assert client.get(f"/api/v1/pets/{pet_id}/portrait-settings").json()["per_day"] == 3

    def test_invalid_window_returns_400(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)

        response = client.put(
            f"/api/v1/pets/{pet_id}/portrait-settings",
            json={"start_hour": 20, "end_hour": 9},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_unknown_pet_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/pets/nope/portrait-settings")

        assert response.status_code == 404


class TestFeedback:
    def test_like_is_recorded_once(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)
        _scan(client)
        shot_id = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"][0]["id"]

        first = client.post(f"/api/v1/portraits/{shot_id}/feedback", json={"kind": "like"})
        second = client.post(f"/api/v1/portraits/{shot_id}/feedback", json={"kind": "like"})

        assert first.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    def test_crop_head_keeps_box(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)
        _scan(client)
        shot_id = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"][0]["id"]

        body = client.post(
            f"/api/v1/portraits/{shot_id}/feedback",
            json={"kind": "crop_head", "crop_box": [10, 20, 110, 120]},
        ).json()

        assert body["crop_box"] == [10, 20, 110, 120]

    def test_unknown_kind_returns_400(self, client: TestClient) -> None:
        pet_id, _ = _prepare(client)
        _scan(client)
        shot_id = client.get(f"/api/v1/pets/{pet_id}/portraits/today").json()["items"][0]["id"]

        response = client.post(
            f"/api/v1/portraits/{shot_id}/feedback", json={"kind": "wow"}
        )

        assert response.status_code == 400

    def test_unknown_shot_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/portraits/nope/feedback", json={"kind": "like"}
        )

        assert response.status_code == 404
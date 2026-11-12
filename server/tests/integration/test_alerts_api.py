"""推送设备、提醒查询与上传自动流水线的集成测试。"""

from __future__ import annotations

from typing import cast

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction


def make_jpeg(*, brightness: int = 180, size: int = 96) -> bytes:
    pixels = np.full((size, size, 3), brightness, dtype=np.uint8)
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


class _FakeClassifier:
    name = "fake-state-classifier"

    def __init__(self, state: ShedState, confidence: float) -> None:
        self._state = state
        self._confidence = confidence

    def classify(self, frame: ImageFrame) -> StatePrediction:
        others = (1.0 - self._confidence) / 2.0
        probabilities = {"normal": others, "opaque": others, "shedding": others}
        probabilities[self._state.value] = self._confidence
        return StatePrediction(
            state=self._state,
            confidence=self._confidence,
            probabilities=probabilities,
        )


def _upload(client: TestClient, payload: bytes, device_id: str) -> httpx.Response:
    return cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", payload, "image/jpeg")},
            headers={"X-Device-Id": device_id},
        ),
    )


class TestDevices:
    def test_register_then_delete(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/devices",
            json={"expo_push_token": "ExponentPushToken[abc]", "platform": "ios"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["expo_push_token"] == "ExponentPushToken[abc]"
        device_pk = body["id"]

        deleted = client.delete(f"/api/v1/devices/{device_pk}")
        assert deleted.status_code == 204
        again = client.delete(f"/api/v1/devices/{device_pk}")
        assert again.status_code == 404

    def test_rejects_unknown_platform(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/devices",
            json={"expo_push_token": "tok", "platform": "palm"},
        )
        assert response.status_code == 400

    def test_register_without_push_token_binds_device(self, client: TestClient) -> None:
        """没开系统通知也要能绑定设备与宠物（提醒进列表、不弹通知）。"""
        response = client.post(
            "/api/v1/devices",
            json={"platform": "android", "device_id": "dev-x"},
        )
        assert response.status_code == 201
        assert response.json()["expo_push_token"] == ""


class TestAlertsQuery:
    def test_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/alerts")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_patch_unknown_returns_404(self, client: TestClient) -> None:
        response = client.patch("/api/v1/alerts/nope", json={"read": True})
        assert response.status_code == 404


class TestUploadPipeline:
    def test_shedding_upload_creates_alert_once(self, client: TestClient) -> None:
        client.app.state.state_classifier = _FakeClassifier(  # type: ignore[attr-defined]
            ShedState.SHEDDING, 0.95
        )
        payload = make_jpeg(brightness=200)

        first = _upload(client, payload, "smoke-device")
        assert first.status_code == 201

        alerts = client.get("/api/v1/alerts", params={"device_id": "smoke-device"}).json()
        assert len(alerts["items"]) == 1
        created = alerts["items"][0]
        assert created["state"] == "shedding"
        assert created["kind"] == "shedding_detected"

        # 重复上传同一张图：走幂等分支，不触发流水线，不新增提醒。
        second = _upload(client, payload, "smoke-device")
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        alerts_after = client.get(
            "/api/v1/alerts", params={"device_id": "smoke-device"}
        ).json()
        assert len(alerts_after["items"]) == 1

    def test_normal_upload_creates_no_alert(self, client: TestClient) -> None:
        client.app.state.state_classifier = _FakeClassifier(  # type: ignore[attr-defined]
            ShedState.NORMAL, 0.95
        )
        response = _upload(client, make_jpeg(brightness=150), "calm-device")
        assert response.status_code == 201
        alerts = client.get("/api/v1/alerts", params={"device_id": "calm-device"}).json()
        assert alerts["items"] == []

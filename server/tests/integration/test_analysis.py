"""体表信号分析接口的集成测试。"""

from __future__ import annotations

from typing import cast

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame


def make_jpeg(*, brightness: int = 180, size: int = 96) -> bytes:
    pixels = np.full((size, size, 3), brightness, dtype=np.uint8)
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


def _upload(
    client: TestClient,
    payload: bytes,
    *,
    captured_at: str | None = None,
) -> httpx.Response:
    headers = {"X-Captured-At": captured_at} if captured_at else {}
    return cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", payload, "image/jpeg")},
            headers=headers,
        ),
    )


def _analyze(client: TestClient, image_id: str) -> httpx.Response:
    return cast(httpx.Response, client.post(f"/api/v1/analysis/{image_id}"))


def test_analyze_returns_bright_body_metrics(client: TestClient) -> None:
    image_id = _upload(client, make_jpeg(brightness=200)).json()["id"]

    response = _analyze(client, image_id)

    assert response.status_code == 200
    body = response.json()
    assert body["detected"] is True
    assert body["metrics_version"] == "1"
    assert body["lightness_mean"] > 75.0
    assert body["high_light_ratio"] > 0.8
    assert body["exposure_scale"] == 1.0
    assert body["normalized"] is False


def test_analyze_is_idempotent(client: TestClient) -> None:
    image_id = _upload(client, make_jpeg()).json()["id"]

    first = _analyze(client, image_id).json()
    second = _analyze(client, image_id).json()

    assert first["computed_at_utc"] == second["computed_at_utc"]


def test_analyze_unknown_image_returns_404(client: TestClient) -> None:
    response = _analyze(client, "does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


class _RejectingDetector:
    name = "rejecting"

    def detect(self, frame: ImageFrame) -> Detection | None:
        return None


def test_analyze_records_empty_metric_when_not_detected(client: TestClient) -> None:
    client.app.state.detector = _RejectingDetector()  # type: ignore[attr-defined]
    image_id = _upload(client, make_jpeg()).json()["id"]

    body = _analyze(client, image_id).json()

    assert body["detected"] is False
    assert body["box"] is None
    assert body["lightness_mean"] is None
    assert body["detector_name"] == "rejecting"


def test_second_day_uses_background_reference(client: TestClient) -> None:
    dark = _upload(
        client, make_jpeg(brightness=100), captured_at="2026-10-31T20:00:00+08:00"
    ).json()
    bright = _upload(
        client, make_jpeg(brightness=130), captured_at="2026-11-01T20:00:00+08:00"
    ).json()
    dark_body = _analyze(client, dark["id"]).json()

    body = _analyze(client, bright["id"]).json()

    assert dark_body["normalized"] is False
    assert body["normalized"] is True
    assert body["exposure_scale"] > 1.0
    # 归一化后应当回到基线的亮度水平，否则说明曝光校正方向反了
    assert body["lightness_mean"] == pytest.approx(dark_body["lightness_mean"], abs=3.0)
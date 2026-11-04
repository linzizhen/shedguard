"""蜕皮状态识别接口的集成测试。"""

from __future__ import annotations

from typing import cast

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction

DEVICE = "cam-shed"
SERIES = f"/api/v1/series/{DEVICE}/shedding"
ALL_STATES = ("normal", "opaque", "shedding")


def make_jpeg(*, brightness: int = 180, size: int = 96) -> bytes:
    pixels = np.full((size, size, 3), brightness, dtype=np.uint8)
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


class _FakeClassifier:
    """固定输出的分类器替身，用来验证服务层的编排而不是模型本身。"""

    def __init__(self, state: ShedState = ShedState.SHEDDING, confidence: float = 0.9):
        self.state = state
        self.confidence = confidence

    @property
    def name(self) -> str:
        return "fake-classifier"

    def classify(self, _frame: ImageFrame) -> StatePrediction:
        remaining = (1.0 - self.confidence) / (len(ALL_STATES) - 1)
        probabilities = {label: remaining for label in ALL_STATES}
        probabilities[self.state.value] = self.confidence
        return StatePrediction(
            state=self.state,
            confidence=self.confidence,
            probabilities=probabilities,
        )


class _RejectingDetector:
    name = "rejecting"

    def detect(self, frame: ImageFrame) -> Detection | None:
        return None


def _upload(
    client: TestClient,
    payload: bytes,
    *,
    captured_at: str | None = None,
) -> str:
    headers = {"X-Device-Id": DEVICE}
    if captured_at is not None:
        headers["X-Captured-At"] = captured_at
    response = cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", payload, "image/jpeg")},
            headers=headers,
        ),
    )
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


def _classify(client: TestClient, image_id: str) -> httpx.Response:
    return cast(httpx.Response, client.post(f"/api/v1/shedding/{image_id}"))


def _series(client: TestClient, *, start: str, end: str) -> httpx.Response:
    return cast(
        httpx.Response,
        client.get(SERIES, params={"from": start, "to": end}),
    )


def _use(client: TestClient, state: ShedState, confidence: float = 0.9) -> None:
    client.app.state.state_classifier = _FakeClassifier(state, confidence)  # type: ignore[attr-defined]


def test_classify_returns_the_state(client: TestClient) -> None:
    _use(client, ShedState.SHEDDING)
    image_id = _upload(client, make_jpeg())

    response = _classify(client, image_id)

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "shedding"
    assert body["confidence"] == pytest.approx(0.9, abs=1e-4)
    assert set(body["probabilities"]) == set(ALL_STATES)
    assert body["classifier_name"] == "fake-classifier"
    assert body["state_version"] == "1"
    assert body["box"] is not None


def test_classify_is_idempotent(client: TestClient) -> None:
    _use(client, ShedState.OPAQUE)
    image_id = _upload(client, make_jpeg())

    first = _classify(client, image_id).json()
    second = _classify(client, image_id).json()

    assert first["computed_at_utc"] == second["computed_at_utc"]
    assert first["state"] == second["state"]


def test_classify_without_a_model_returns_503(client: TestClient) -> None:
    image_id = _upload(client, make_jpeg())

    response = _classify(client, image_id)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_classify_unknown_image_returns_404(client: TestClient) -> None:
    _use(client, ShedState.NORMAL)

    response = _classify(client, "does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_low_confidence_falls_back_to_unknown(client: TestClient) -> None:
    _use(client, ShedState.SHEDDING, confidence=0.3)
    image_id = _upload(client, make_jpeg())

    body = _classify(client, image_id).json()

    assert body["state"] == "unknown"
    assert body["confidence"] is None
    # 概率分布仍然保留，方便排查「模型看到了什么」。
    assert body["probabilities"] is not None


def test_missing_detection_falls_back_to_unknown(client: TestClient) -> None:
    _use(client, ShedState.SHEDDING)
    client.app.state.detector = _RejectingDetector()  # type: ignore[attr-defined]
    image_id = _upload(client, make_jpeg())

    body = _classify(client, image_id).json()

    assert body["state"] == "unknown"
    assert body["box"] is None
    assert body["probabilities"] is None
    assert body["detector_name"] == "rejecting"


def test_series_derives_events_from_state_changes(client: TestClient) -> None:
    plan = [
        ("2026-11-01T12:00:00+08:00", ShedState.NORMAL, 120),
        ("2026-11-02T12:00:00+08:00", ShedState.OPAQUE, 140),
        ("2026-11-03T12:00:00+08:00", ShedState.NORMAL, 160),
    ]
    for captured_at, state, brightness in plan:
        _use(client, state)
        image_id = _upload(
            client, make_jpeg(brightness=brightness), captured_at=captured_at
        )
        assert _classify(client, image_id).status_code == 200

    body = _series(client, start="2026-11-01", end="2026-11-03").json()

    assert [day["state"] for day in body["days"]] == ["normal", "opaque", "normal"]
    assert body["days"][1]["votes"]["opaque"] == 1
    assert [event["type"] for event in body["events"]] == [
        "shed_started",
        "shed_completed",
    ]
    assert body["events"][0]["date"] == "2026-11-02"
    assert body["events"][1]["date"] == "2026-11-03"
    assert body["current_state"] == "normal"


def test_series_reports_null_for_days_without_images(client: TestClient) -> None:
    _use(client, ShedState.NORMAL)
    first = _upload(
        client, make_jpeg(brightness=120), captured_at="2026-11-01T12:00:00+08:00"
    )
    _classify(client, first)

    body = _series(client, start="2026-11-01", end="2026-11-02").json()

    assert body["days"][0]["state"] == "normal"
    assert body["days"][1]["state"] is None
    assert body["days"][1]["image_count"] == 0
    assert body["days"][1]["votes"] == {"normal": 0, "opaque": 0, "shedding": 0}
    assert body["events"] == []


def test_series_rejects_a_reversed_range(client: TestClient) -> None:
    response = _series(client, start="2026-11-05", end="2026-11-01")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_series_rejects_a_malformed_date(client: TestClient) -> None:
    response = _series(client, start="2026-1-1", end="2026-11-02")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_series_of_an_unknown_device_is_all_null(client: TestClient) -> None:
    body = _series(client, start="2026-11-01", end="2026-11-02").json()

    assert all(day["state"] is None for day in body["days"])
    assert body["current_state"] is None

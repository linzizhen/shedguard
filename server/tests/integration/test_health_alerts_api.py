"""设备健康兜底提醒的集成测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from shedguard_server.infra.push import SkippedPushGateway
from shedguard_server.services.health import scan_once

#: 2026-11-12 14:00 本地（UTC+8），落在默认活跃时段 08–20 内。
NOW = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)


def _jpeg() -> bytes:
    pixels = np.full((96, 96, 3), 180, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.tobytes()


def _register(client: TestClient, device_id: str) -> None:
    response = client.post(
        "/api/v1/devices",
        json={
            "expo_push_token": f"ExponentPushToken[{device_id}]",
            "platform": "android",
            "device_id": device_id,
        },
    )
    assert response.status_code == 201, response.text


def _upload(client: TestClient, captured_at: datetime) -> None:
    response = cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
            headers={
                "X-Device-Id": "dev-1",
                "X-Captured-At": captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ),
    )
    assert response.status_code == 201, response.text


def _scan(client: TestClient, now: datetime = NOW) -> int:
    return scan_once(
        session_factory=client.app.state.session_factory,  # type: ignore[attr-defined]
        settings=client.app.state.settings,  # type: ignore[attr-defined]
        gateway=SkippedPushGateway(),
        now=now,
    )


class TestDeviceSilent:
    def test_creates_alert_when_silent(self, client: TestClient) -> None:
        _register(client, "dev-1")
        _upload(client, NOW - timedelta(hours=7))

        assert _scan(client) == 1

        alerts = client.get("/api/v1/alerts").json()["items"]
        kinds = [item["kind"] for item in alerts]
        assert kinds.count("device_silent") == 1

    def test_dedupes_on_second_scan(self, client: TestClient) -> None:
        _register(client, "dev-1")
        _upload(client, NOW - timedelta(hours=7))

        assert _scan(client) == 1
        assert _scan(client) == 0

        alerts = client.get("/api/v1/alerts").json()["items"]
        assert [item["kind"] for item in alerts].count("device_silent") == 1

    def test_no_alert_when_recent_upload(self, client: TestClient) -> None:
        _register(client, "dev-1")
        _upload(client, NOW - timedelta(hours=1))

        assert _scan(client) == 0


class TestMonitorDisabled:
    def test_no_background_task(self, client: TestClient) -> None:
        # 测试配置里 health_monitor_enabled=False，启动时不应创建后台任务。
        assert getattr(client.app.state, "health_task", None) is None  # type: ignore[attr-defined]

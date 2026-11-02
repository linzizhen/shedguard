"""信号接口集成测试：验证判定层与 HTTP 层的接线与序列化。

这里直接写入 ``frame_metrics`` 行，而不走「上传图片 → 分析」链路。原因是
分析链路会做曝光归一化——整幅图变亮会被当成灯光变化校正掉，而蜕皮信号
应该是「背景不变、身体变白」。构造后者需要真实的框内/框外分区，属于
M5 的测试范围；本文件只关心判定层拿到指标之后的行为。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import cv2
import httpx
import numpy as np
import pytest

from shedguard_server.domain.models import FrameMetric
from shedguard_server.infra.repository import FrameMetricRepository

START = date(2026, 1, 1)
DEVICE = "cam-judge"

BASE: dict[str, float] = {
    "lightness_mean": 40.0,
    "lightness_std": 8.0,
    "saturation_mean": 30.0,
    "high_light_ratio": 0.10,
    "edge_density": 0.20,
    "color_entropy": 3.0,
}

JITTER: dict[str, float] = {
    "lightness_mean": 1.0,
    "lightness_std": 0.5,
    "saturation_mean": 1.0,
    "high_light_ratio": 0.02,
    "edge_density": 0.02,
    "color_entropy": 0.2,
}


def make_jpeg(*, brightness: int = 120, size: int = 64, marker: int = 0) -> bytes:
    """生成一张 JPEG。``marker`` 只改一个角落像素，用于制造不同的字节内容。"""
    array = np.full((size, size, 3), brightness, dtype=np.uint8)
    array[0, 0] = (marker % 256, (marker // 256) % 256, 0)
    ok, buffer = cv2.imencode(".jpg", array)
    assert ok
    return buffer.tobytes()


def _stable(index: int) -> dict[str, float]:
    sign = 1.0 if index % 2 == 0 else -1.0
    return {name: BASE[name] + sign * JITTER[name] for name in BASE}


def _daily_values(index: int, bumps: dict[int, dict[str, float]]) -> dict[str, float]:
    values = _stable(index)
    for name, delta in bumps.get(index, {}).items():
        values[name] = BASE[name] + delta
    return values


def _upload_image(client: httpx.Client, *, local_date: date, marker: int) -> str:
    # 亮度随 marker 微调，保证每张图字节不同，否则 SHA-256 会判为重复上传。
    response = client.post(
        "/api/v1/images",
        content=make_jpeg(brightness=100 + marker),
        headers={
            "Content-Type": "image/jpeg",
            "X-Device-Id": DEVICE,
            "X-Captured-At": f"{local_date.isoformat()}T20:00:00+08:00",
        },
    )
    assert response.status_code == 201, response.text
    image_id: str = response.json()["id"]
    return image_id


def _seed(
    client: httpx.Client,
    *,
    days: int,
    bumps: dict[int, dict[str, float]] | None = None,
    skip: set[int] | None = None,
) -> None:
    """为前 ``days`` 天各写一帧指标，``skip`` 中的日期不写。"""
    bumps = bumps or {}
    skip = skip or set()
    factory = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        repository = FrameMetricRepository(session)
        for index in range(days):
            if index in skip:
                continue
            local_date = START + timedelta(days=index)
            values = _daily_values(index, bumps)
            repository.save(
                FrameMetric(
                    image_id=_upload_image(client, local_date=local_date, marker=index),
                    device_id=DEVICE,
                    local_date=local_date,
                    detected=True,
                    box=(0, 0, 64, 64),
                    detector_name="null-detector",
                    detector_confidence=None,
                    normalized=False,
                    exposure_scale=1.0,
                    background_lightness=120.0,
                    computed_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
                    metrics_version="1",
                    **values,
                )
            )


def _signals(client: httpx.Client, *, start: date, end: date) -> dict[str, object]:
    response = client.get(
        f"/api/v1/series/{DEVICE}/signals",
        params={"from": start.isoformat(), "to": end.isoformat()},
    )
    assert response.status_code == 200, response.text
    payload: dict[str, object] = response.json()
    return payload


def test_signals_requires_two_hits_for_two_days_to_alert(client: httpx.Client) -> None:
    bumps = {
        14: {"lightness_mean": 6.0, "saturation_mean": -10.0},
        15: {"lightness_mean": 6.0, "saturation_mean": -10.0},
    }
    _seed(client, days=16, bumps=bumps)

    payload = _signals(client, start=START + timedelta(days=7), end=START + timedelta(days=15))
    days = payload["days"]
    assert isinstance(days, list)

    watch_day = days[7]
    alert_day = days[8]
    assert watch_day["state"] == "watch"
    assert alert_day["state"] == "alert"
    assert alert_day["hits"] == ["lightness_mean", "saturation_mean"]
    assert payload["alert_days"] == 1
    assert payload["current_state"] == "alert"


def test_single_day_bump_only_reaches_watch(client: httpx.Client) -> None:
    bumps = {14: {"lightness_mean": 6.0, "saturation_mean": -10.0}}
    _seed(client, days=16, bumps=bumps)

    payload = _signals(client, start=START + timedelta(days=7), end=START + timedelta(days=15))
    days = payload["days"]
    assert isinstance(days, list)

    assert days[7]["state"] == "watch"
    assert days[8]["state"] == "normal"
    assert payload["alert_days"] == 0


def test_missing_day_breaks_streak(client: httpx.Client) -> None:
    bumps = {
        14: {"lightness_mean": 6.0, "saturation_mean": -10.0},
        16: {"lightness_mean": 12.0, "saturation_mean": -15.0},
    }
    _seed(client, days=18, bumps=bumps, skip={15})

    payload = _signals(client, start=START + timedelta(days=7), end=START + timedelta(days=17))
    days = payload["days"]
    assert isinstance(days, list)

    assert days[7]["state"] == "watch"
    assert days[8]["image_id"] is None
    assert days[8]["state"] == "insufficient"
    # 缺日清零后重新从 watch 开始，而不是直接 alert。
    assert days[9]["state"] == "watch"


def test_insufficient_when_baseline_too_thin(client: httpx.Client) -> None:
    _seed(client, days=3)

    payload = _signals(client, start=START, end=START + timedelta(days=2))
    days = payload["days"]
    assert isinstance(days, list)
    assert [item["state"] for item in days] == ["insufficient"] * 3
    assert payload["current_state"] == "insufficient"


def test_unknown_device_reports_insufficient(client: httpx.Client) -> None:
    response = client.get(
        "/api/v1/series/nobody/signals",
        params={"from": "2026-01-01", "to": "2026-01-03"},
    )
    assert response.status_code == 200
    payload = response.json()
    # 一张图都没有时必须说「判断不了」，而不是报「正常」。
    assert payload["current_state"] == "insufficient"
    assert payload["alert_days"] == 0
    assert all(item["image_id"] is None for item in payload["days"])
    assert all(item["state"] == "insufficient" for item in payload["days"])


def test_reversed_range_is_rejected(client: httpx.Client) -> None:
    response = client.get(
        f"/api/v1/series/{DEVICE}/signals",
        params={"from": "2026-02-01", "to": "2026-01-01"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_bad_date_is_rejected(client: httpx.Client) -> None:
    response = client.get(
        f"/api/v1/series/{DEVICE}/signals",
        params={"from": "2026/01/01", "to": "2026-01-02"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_metrics_are_rounded(client: httpx.Client) -> None:
    _seed(client, days=10)
    payload = _signals(client, start=START + timedelta(days=7), end=START + timedelta(days=9))
    days = payload["days"]
    assert isinstance(days, list)
    lightness = days[0]["metrics"]["lightness_mean"]
    assert isinstance(lightness, float)
    assert len(str(lightness).split(".")[-1]) <= 4


@pytest.mark.parametrize("device_id", ["bad device", "x" * 65])
def test_invalid_device_id_is_rejected(client: httpx.Client, device_id: str) -> None:
    response = client.get(
        f"/api/v1/series/{device_id}/signals",
        params={"from": "2026-01-01", "to": "2026-01-02"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
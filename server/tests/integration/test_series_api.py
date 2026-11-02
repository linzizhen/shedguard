"""序列接口集成测试：代表帧选择、缺失日补全、参数校验。"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient


def _jpeg() -> bytes:
    """造一段可通过魔数校验且内容唯一的 JPEG。"""
    return b"\xff\xd8\xff\xe0" + os.urandom(24)


def _upload(
    client: TestClient,
    *,
    captured_at: str,
    device_id: str = "cam-1",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/images",
        content=_jpeg(),
        headers={"X-Device-Id": device_id, "X-Captured-At": captured_at},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _series(client: TestClient, device_id: str, start: str, end: str) -> dict[str, object]:
    response = client.get(
        "/api/v1/series",
        params={"device_id": device_id, "from": start, "to": end},
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_picks_closest_frame_within_window(client: TestClient) -> None:
    near = _upload(client, captured_at="2026-11-01T20:10:00+08:00")
    _upload(client, captured_at="2026-11-01T21:40:00+08:00")
    _upload(client, captured_at="2026-11-01T11:00:00+08:00")

    body = _series(client, "cam-1", "2026-11-01", "2026-11-01")

    days = body["days"]
    assert isinstance(days, list)
    assert len(days) == 1
    day = days[0]
    assert day["image_id"] == near["id"]
    assert day["in_window"] is True
    assert day["total_images"] == 3
    assert body["missing_days"] == 0


def test_fills_missing_days_and_marks_them(client: TestClient) -> None:
    first = _upload(client, captured_at="2026-11-01T20:05:00+08:00")
    third = _upload(client, captured_at="2026-11-03T20:05:00+08:00")

    body = _series(client, "cam-1", "2026-11-01", "2026-11-03")

    days = body["days"]
    assert isinstance(days, list)
    assert [day["date"] for day in days] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert days[1]["image_id"] is None
    assert days[1]["in_window"] is False
    assert days[0]["image_id"] == first["id"]
    assert days[2]["image_id"] == third["id"]
    assert body["total_days"] == 3
    assert body["missing_days"] == 1


def test_out_of_window_frame_is_returned_and_flagged(client: TestClient) -> None:
    record = _upload(client, captured_at="2026-11-01T03:00:00+08:00")

    body = _series(client, "cam-1", "2026-11-01", "2026-11-01")

    days = body["days"]
    assert isinstance(days, list)
    assert days[0]["image_id"] == record["id"]
    assert days[0]["in_window"] is False


def test_isolates_devices(client: TestClient) -> None:
    _upload(client, captured_at="2026-11-01T20:05:00+08:00", device_id="cam-1")

    body = _series(client, "cam-2", "2026-11-01", "2026-11-01")

    days = body["days"]
    assert isinstance(days, list)
    assert days[0]["image_id"] is None
    assert body["missing_days"] == 1


def test_rejects_reversed_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/series",
        params={"device_id": "cam-1", "from": "2026-11-03", "to": "2026-11-01"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_rejects_overlong_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/series",
        params={"device_id": "cam-1", "from": "2026-01-01", "to": "2027-01-03"},
    )

    assert response.status_code == 400
    assert "366" in response.json()["error"]["message"]


def test_rejects_bad_date_format(client: TestClient) -> None:
    response = client.get(
        "/api/v1/series",
        params={"device_id": "cam-1", "from": "2026/11/01", "to": "2026-11-02"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_rejects_invalid_device_id(client: TestClient) -> None:
    response = client.get(
        "/api/v1/series",
        params={"device_id": "bad id", "from": "2026-11-01", "to": "2026-11-02"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_requires_from_and_to(client: TestClient) -> None:
    response = client.get("/api/v1/series", params={"device_id": "cam-1"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
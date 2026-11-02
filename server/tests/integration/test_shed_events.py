"""蜕皮事件接口集成测试：新建、覆盖、查询与参数校验。"""

from __future__ import annotations

from typing import cast

import httpx
from fastapi.testclient import TestClient


def _put(
    client: TestClient,
    *,
    device_id: str = "cam-1",
    event_date: str = "2026-11-05",
    outcome: str = "completed",
    notes: str | None = None,
) -> httpx.Response:
    payload: dict[str, object] = {"outcome": outcome}
    if notes is not None:
        payload["notes"] = notes
    url = f"/api/v1/shed-events/{device_id}/{event_date}"
    return cast(httpx.Response, client.put(url, json=payload))


def test_creates_event(client: TestClient) -> None:
    response = _put(client, notes="  整体顺利  ")

    assert response.status_code == 201
    body = response.json()
    assert body["device_id"] == "cam-1"
    assert body["event_date"] == "2026-11-05"
    assert body["outcome"] == "completed"
    assert body["notes"] == "整体顺利"
    assert body["created_at_utc"].endswith("Z")
    assert body["updated_at_utc"].endswith("Z")


def test_second_put_overwrites_without_changing_id(client: TestClient) -> None:
    first = _put(client, outcome="partial", notes="尾部残留").json()

    second = _put(client, outcome="completed", notes="已蜕完")

    assert second.status_code == 200
    body = second.json()
    assert body["id"] == first["id"]
    assert body["outcome"] == "completed"
    assert body["notes"] == "已蜕完"
    assert body["created_at_utc"] == first["created_at_utc"]


def test_lists_all_events_by_device(client: TestClient) -> None:
    _put(client, device_id="cam-1", event_date="2026-11-05")
    _put(client, device_id="cam-1", event_date="2026-10-01")
    _put(client, device_id="cam-2", event_date="2026-10-15")

    response = client.get("/api/v1/shed-events", params={"device_id": "cam-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["event_date"] for item in body["items"]] == ["2026-11-05", "2026-10-01"]


def test_filters_by_date_range(client: TestClient) -> None:
    _put(client, event_date="2026-09-01")
    _put(client, event_date="2026-10-01")
    _put(client, event_date="2026-11-01")

    response = client.get(
        "/api/v1/shed-events",
        params={"from": "2026-09-15", "to": "2026-10-31"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["event_date"] == "2026-10-01"


def test_lists_everything_without_filters(client: TestClient) -> None:
    _put(client, device_id="cam-1")
    _put(client, device_id="cam-2", event_date="2026-11-06")

    response = client.get("/api/v1/shed-events")

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_rejects_unknown_outcome(client: TestClient) -> None:
    response = _put(client, outcome="done")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "outcome" in body["error"]["message"]


def test_rejects_too_long_notes(client: TestClient) -> None:
    response = _put(client, notes="x" * 2001)

    assert response.status_code == 400
    assert "2000" in response.json()["error"]["message"]


def test_rejects_bad_event_date(client: TestClient) -> None:
    response = _put(client, event_date="20261105")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_rejects_missing_outcome(client: TestClient) -> None:
    response = client.put("/api/v1/shed-events/cam-1/2026-11-05", json={"notes": "x"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_rejects_invalid_device_id_in_query(client: TestClient) -> None:
    response = client.get("/api/v1/shed-events", params={"device_id": "bad id"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
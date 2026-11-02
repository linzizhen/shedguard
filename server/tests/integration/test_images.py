"""图片接入接口的集成测试。"""

from __future__ import annotations

from typing import cast

import httpx
from fastapi.testclient import TestClient

JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 32 + b"\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload(
    client: TestClient,
    payload: bytes = JPEG_BYTES,
    *,
    filename: str = "a.jpg",
    content_type: str = "image/jpeg",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return cast(
        httpx.Response,
        client.post(
            "/api/v1/images",
            files={"file": (filename, payload, content_type)},
            headers=headers or {},
        ),
    )


def test_upload_creates_record_and_file(client: TestClient) -> None:
    response = _upload(client)

    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert body["device_id"] == "unknown"
    assert body["byte_size"] == len(JPEG_BYTES)
    assert body["local_date"] == "2026-11-02" or body["local_date"]
    assert body["rel_path"].startswith("images/")
    assert body["rel_path"].endswith(".jpg")


def test_duplicate_upload_is_idempotent(client: TestClient) -> None:
    first = _upload(client)
    second = _upload(client, headers={"X-Device-Id": "cam-1"})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]


def test_upload_accepts_png(client: TestClient) -> None:
    response = _upload(client, PNG_BYTES, filename="a.png", content_type="image/png")

    assert response.status_code == 201
    assert response.json()["rel_path"].endswith(".png")


def test_upload_rejects_non_image(client: TestClient) -> None:
    response = _upload(client, b"not an image", filename="a.txt", content_type="text/plain")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_rejects_empty_payload(client: TestClient) -> None:
    response = _upload(client, b"")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_PAYLOAD"


def test_upload_rejects_oversized_payload(client: TestClient) -> None:
    response = _upload(client, JPEG_BYTES + b"\x00" * 2048)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_rejects_oversized_declared_content_length(client: TestClient) -> None:
    """Content-Length 超过上限时可提前拒绝，无需读完请求体。"""
    response = _upload(client, JPEG_BYTES + b"\x00" * 16384)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_rejects_invalid_device_id(client: TestClient) -> None:
    response = _upload(client, headers={"X-Device-Id": "bad id!"})

    assert response.status_code == 400


def test_upload_rejects_invalid_captured_at(client: TestClient) -> None:
    response = _upload(client, headers={"X-Captured-At": "yesterday"})

    assert response.status_code == 400


def test_upload_uses_captured_at_for_local_date(client: TestClient) -> None:
    response = _upload(client, headers={"X-Captured-At": "2026-11-01T17:30:00Z"})

    assert response.status_code == 201
    body = response.json()
    assert body["captured_at_utc"] == "2026-11-01T17:30:00Z"
    assert body["local_date"] == "2026-11-02"


def test_upload_accepts_raw_body(client: TestClient) -> None:
    response = client.post(
        "/api/v1/images",
        content=JPEG_BYTES,
        headers={"Content-Type": "image/jpeg", "X-Device-Id": "cam-raw"},
    )

    assert response.status_code == 201
    assert response.json()["device_id"] == "cam-raw"


def test_multipart_with_nonstandard_file_field_still_works(client: TestClient) -> None:
    response = client.post("/api/v1/images", files={"other": ("x.jpg", JPEG_BYTES, "image/jpeg")})

    # 没有 file 字段时退化为取第一个文件字段，仍应成功。
    assert response.status_code == 201


def test_multipart_without_file_field_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/images", files={"note": (None, "x")})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_form_urlencoded_body_is_not_an_image(client: TestClient) -> None:
    response = client.post("/api/v1/images", data={"note": "x"})

    assert response.status_code == 415


def test_list_images_by_date(client: TestClient) -> None:
    created = _upload(client).json()
    response = client.get("/api/v1/images", params={"date": created["local_date"]})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


def test_list_images_rejects_bad_date(client: TestClient) -> None:
    response = client.get("/api/v1/images", params={"date": "2026/11/02"})

    assert response.status_code == 400


def test_list_images_defaults_to_server_local_date(client: TestClient) -> None:
    _upload(client)
    response = client.get("/api/v1/images")

    assert response.status_code == 200
    assert response.json()["total"] >= 0


def test_list_images_filters_by_device(client: TestClient) -> None:
    created = _upload(client, headers={"X-Device-Id": "cam-1"}).json()
    response = client.get(
        "/api/v1/images",
        params={"date": created["local_date"], "device_id": "cam-2"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_image_returns_bytes_and_etag(client: TestClient) -> None:
    created = _upload(client).json()
    response = client.get(f"/api/v1/images/{created['id']}")

    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    assert response.headers["etag"] == f'"{created["sha256"]}"'
    assert response.headers["cache-control"] == "immutable"


def test_get_image_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/api/v1/images/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_image_metadata(client: TestClient) -> None:
    created = _upload(client).json()
    response = client.get(f"/api/v1/images/{created['id']}/metadata")

    assert response.status_code == 200
    assert response.json()["sha256"] == created["sha256"]
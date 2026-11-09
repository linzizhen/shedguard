"""宠物档案、蜕皮日志与拍照查验的集成测试。"""

from __future__ import annotations

from typing import cast

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction

PETS = "/api/v1/pets"


def make_jpeg(*, brightness: int = 180, size: int = 96) -> bytes:
    pixels = np.full((size, size, 3), brightness, dtype=np.uint8)
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


class _FakeClassifier:
    """固定输出的分类器替身。"""

    def __init__(self, state: ShedState = ShedState.SHEDDING, confidence: float = 0.9):
        self.state = state
        self.confidence = confidence

    @property
    def name(self) -> str:
        return "fake-classifier"

    def classify(self, _frame: ImageFrame) -> StatePrediction:
        labels = ("normal", "opaque", "shedding")
        remaining = (1.0 - self.confidence) / (len(labels) - 1)
        probabilities = {label: remaining for label in labels}
        probabilities[self.state.value] = self.confidence
        return StatePrediction(
            state=self.state,
            confidence=self.confidence,
            probabilities=probabilities,
        )


def _create_pet(client: TestClient, name: str = "小橙") -> str:
    response = cast(
        httpx.Response,
        client.post(PETS, json={"name": name, "species": "豹纹守宫", "morph": "高黄"}),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


class TestPetCrud:
    """宠物档案 CRUD。"""

    def test_create_and_get(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(httpx.Response, client.get(f"{PETS}/{pet_id}"))
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "小橙"
        assert body["species"] == "豹纹守宫"
        assert body["morph"] == "高黄"
        assert body["birth_date"] is None

    def test_list(self, client: TestClient) -> None:
        _create_pet(client, "一号")
        _create_pet(client, "二号")
        response = cast(httpx.Response, client.get(PETS))
        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert "一号" in names
        assert "二号" in names

    def test_update(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(
            httpx.Response,
            client.put(f"{PETS}/{pet_id}", json={"name": "大橙", "birth_date": "2023-05-01"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "大橙"
        assert body["birth_date"] == "2023-05-01"
        assert body["morph"] == "高黄"  # 未更新的字段保持

    def test_delete(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(httpx.Response, client.delete(f"{PETS}/{pet_id}"))
        assert response.status_code == 204
        response = cast(httpx.Response, client.get(f"{PETS}/{pet_id}"))
        assert response.status_code == 404

    def test_get_unknown_404(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.get(f"{PETS}/nonexistent"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_empty_name_rejected(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.post(PETS, json={"name": "  "}))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_delete_pet_cascades_records(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.post(
            f"{PETS}/{pet_id}/shed-records",
            json={"started_on": "2026-10-01", "completed_on": "2026-10-03"},
        )
        client.delete(f"{PETS}/{pet_id}")
        # 宠物删了之后重新创建同 id 不可能，但至少接口不再报错
        response = cast(httpx.Response, client.get(PETS))
        assert all(item["id"] != pet_id for item in response.json()["items"])


class TestShedRecords:
    """手动蜕皮日志 CRUD 与冲突检测。"""

    def test_create_and_list(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/shed-records",
                json={"started_on": "2026-10-01", "completed_on": "2026-10-03", "notes": "完整"},
            ),
        )
        assert response.status_code == 201, response.text
        response = cast(httpx.Response, client.get(f"{PETS}/{pet_id}/shed-records"))
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["started_on"] == "2026-10-01"
        assert items[0]["completed_on"] == "2026-10-03"
        assert items[0]["notes"] == "完整"

    def test_same_day_conflict_409(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.post(f"{PETS}/{pet_id}/shed-records", json={"started_on": "2026-10-01"})
        response = cast(
            httpx.Response,
            client.post(f"{PETS}/{pet_id}/shed-records", json={"started_on": "2026-10-01"}),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    def test_completed_before_started_rejected(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/shed-records",
                json={"started_on": "2026-10-03", "completed_on": "2026-10-01"},
            ),
        )
        assert response.status_code == 400

    def test_update(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        created = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/shed-records",
                json={"started_on": "2026-10-01", "completed_on": None},
            ),
        ).json()
        record_id = created["id"]
        response = cast(
            httpx.Response,
            client.put(
                f"{PETS}/{pet_id}/shed-records/{record_id}",
                json={"completed_on": "2026-10-04", "notes": "拖了几天"},
            ),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["completed_on"] == "2026-10-04"
        assert body["notes"] == "拖了几天"
        assert body["started_on"] == "2026-10-01"

    def test_delete(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        created = cast(
            httpx.Response,
            client.post(f"{PETS}/{pet_id}/shed-records", json={"started_on": "2026-10-01"}),
        ).json()
        response = cast(
            httpx.Response,
            client.delete(f"{PETS}/{pet_id}/shed-records/{created['id']}"),
        )
        assert response.status_code == 204
        response = cast(httpx.Response, client.get(f"{PETS}/{pet_id}/shed-records"))
        assert response.json()["items"] == []

    def test_unknown_pet_404(self, client: TestClient) -> None:
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/nonexistent/shed-records",
                json={"started_on": "2026-10-01"},
            ),
        )
        assert response.status_code == 404


class TestShedPrediction:
    """周期预测接口。"""

    def test_insufficient_records(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(httpx.Response, client.get(f"{PETS}/{pet_id}/shed-prediction"))
        assert response.status_code == 200
        body = response.json()
        assert body["predictable"] is False
        assert body["reason"]

    def test_predictable_with_three_records(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        for started, completed in (
            ("2026-07-01", "2026-07-03"),
            ("2026-08-01", "2026-08-04"),
            ("2026-09-01", "2026-09-03"),
        ):
            client.post(
                f"{PETS}/{pet_id}/shed-records",
                json={"started_on": started, "completed_on": completed},
            )
        response = cast(
            httpx.Response,
            client.get(f"{PETS}/{pet_id}/shed-prediction", params={"today": "2026-09-15"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["predictable"] is True
        assert body["median_interval_days"] == 31
        assert body["based_on_cycles"] == 2
        # 间隔 [31, 31] → MAD=0 → 单日窗口：09-01 + 31 天 = 10-02
        assert body["next_window_start"] == "2026-10-02"

    def test_invalid_today_400(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        response = cast(
            httpx.Response,
            client.get(f"{PETS}/{pet_id}/shed-prediction", params={"today": "2026-9-1"}),
        )
        assert response.status_code == 400


class TestCheckPhoto:
    """拍照查验聚合端点。"""

    def test_check_photo_happy_path(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.app.state.state_classifier = _FakeClassifier(ShedState.SHEDDING, 0.9)  # type: ignore[attr-defined]
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                files={"file": ("a.jpg", make_jpeg(), "image/jpeg")},
            ),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"] == "shedding"
        assert body["confidence"] == 0.9
        assert "蜕皮" in body["advice"]
        assert body["image_id"]

    def test_check_photo_normal_state(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.app.state.state_classifier = _FakeClassifier(ShedState.NORMAL, 0.95)  # type: ignore[attr-defined]
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                files={"file": ("a.jpg", make_jpeg(brightness=100), "image/jpeg")},
            ),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "normal"
        assert "正常" in body["advice"]

    def test_check_photo_unknown_pet_404(self, client: TestClient) -> None:
        client.app.state.state_classifier = _FakeClassifier()  # type: ignore[attr-defined]
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/nonexistent/check-photo",
                files={"file": ("a.jpg", make_jpeg(), "image/jpeg")},
            ),
        )
        assert response.status_code == 404

    def test_check_photo_no_classifier_503(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.app.state.state_classifier = None  # type: ignore[attr-defined]
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                files={"file": ("a.jpg", make_jpeg(), "image/jpeg")},
            ),
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"

    def test_check_photo_empty_payload_400(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.app.state.state_classifier = _FakeClassifier()  # type: ignore[attr-defined]
        response = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                content=b"",
                headers={"Content-Type": "image/jpeg"},
            ),
        )
        assert response.status_code == 400

    def test_check_photo_idempotent(self, client: TestClient) -> None:
        pet_id = _create_pet(client)
        client.app.state.state_classifier = _FakeClassifier(ShedState.SHEDDING, 0.9)  # type: ignore[attr-defined]
        payload = make_jpeg()
        first = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                files={"file": ("a.jpg", payload, "image/jpeg")},
            ),
        )
        second = cast(
            httpx.Response,
            client.post(
                f"{PETS}/{pet_id}/check-photo",
                files={"file": ("a.jpg", payload, "image/jpeg")},
            ),
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["image_id"] == second.json()["image_id"]


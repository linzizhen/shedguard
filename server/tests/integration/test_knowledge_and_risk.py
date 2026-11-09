"""知识库与风险评估的集成测试。"""

from __future__ import annotations

from typing import cast

import httpx
from fastapi.testclient import TestClient

KNOWLEDGE = "/api/v1/knowledge"
RISK = "/api/v1/risk-assessment"


class TestKnowledgeApi:
    """知识库接口。"""

    def test_list_topics(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.get(f"{KNOWLEDGE}/topics"))
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 6
        slugs = [item["slug"] for item in items]
        assert slugs[0] == "overview"
        for item in items:
            assert item["title"]
            assert item["summary"]

    def test_get_topic_detail(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.get(f"{KNOWLEDGE}/topics/stuck-shed"))
        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == "stuck-shed"
        assert len(body["sections"]) >= 2
        for section in body["sections"]:
            assert section["heading"]
            assert len(section["bullets"]) >= 2

    def test_unknown_topic_404(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.get(f"{KNOWLEDGE}/topics/nonsense"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestRiskApi:
    """风险评估接口。"""

    def _answers(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "last_shed_complete": "complete",
            "eye_condition": "clear",
            "toe_condition": "normal",
            "hydration": "daily",
            "humidity": "above_50",
            "water_bowl": "fresh_daily",
        }
        base.update(overrides)
        return base

    def test_healthy_answers_low(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.post(RISK, json=self._answers()))
        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 0
        assert body["level"] == "low"
        assert body["vet_warning"] is None

    def test_eye_retained_high_with_warning(self, client: TestClient) -> None:
        response = cast(
            httpx.Response,
            client.post(RISK, json=self._answers(eye_condition="retained_spectacle")),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["level"] == "moderate"
        assert body["vet_warning"] is not None
        assert "医生" in body["vet_warning"]

    def test_invalid_value_400(self, client: TestClient) -> None:
        response = cast(
            httpx.Response,
            client.post(RISK, json=self._answers(toe_condition="broken")),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_missing_field_400(self, client: TestClient) -> None:
        response = cast(httpx.Response, client.post(RISK, json={"eye_condition": "clear"}))
        assert response.status_code == 400

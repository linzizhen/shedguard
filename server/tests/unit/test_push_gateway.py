"""Expo 推送网关的单元测试：用 httpx.MockTransport 拦截网络。"""

from __future__ import annotations

import json

import httpx

from shedguard_server.domain.push import PushMessage, PushStatus
from shedguard_server.infra.push import ExpoPushGateway, SkippedPushGateway

URL = "https://exp.example.test/push"

MESSAGE = PushMessage(to="tok-1", title="守宫正在蜕皮", body="请看照片", data={"alert_id": "a1"})


def gateway_with(handler: object) -> ExpoPushGateway:
    return ExpoPushGateway(URL, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_success_ticket_returns_sent() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"status": "ok", "id": "t1"}]})

    outcome = gateway_with(handler).send(MESSAGE)
    assert outcome.status is PushStatus.SENT
    payload = captured["payload"]
    assert isinstance(payload, list)
    assert payload[0]["to"] == "tok-1"
    assert payload[0]["title"] == "守宫正在蜕皮"
    assert payload[0]["data"] == {"alert_id": "a1"}


def test_device_not_registered_returns_invalid() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "message": "not registered",
                        "details": {"error": "DeviceNotRegistered"},
                    }
                ]
            },
        )

    assert gateway_with(handler).send(MESSAGE).status is PushStatus.INVALID


def test_other_ticket_error_returns_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"status": "error", "message": "boom"}]}
        )

    assert gateway_with(handler).send(MESSAGE).status is PushStatus.FAILED


def test_http_error_returns_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    assert gateway_with(handler).send(MESSAGE).status is PushStatus.FAILED


def test_malformed_body_returns_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    assert gateway_with(handler).send(MESSAGE).status is PushStatus.FAILED


def test_skipped_gateway_returns_skipped() -> None:
    assert SkippedPushGateway().send(MESSAGE).status is PushStatus.SKIPPED

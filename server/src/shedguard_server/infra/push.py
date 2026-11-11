"""Expo 推送网关实现（基于 httpx）。"""

from __future__ import annotations

import httpx

from shedguard_server.domain.push import PushGateway, PushMessage, PushOutcome, PushStatus

DEFAULT_TIMEOUT_SECONDS = 5.0


class ExpoPushGateway(PushGateway):
    """调用 Expo Push API 的网关；失败不会抛异常，而是转成 `PushOutcome`。"""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._transport = transport

    def send(self, message: PushMessage) -> PushOutcome:
        payload = [
            {
                "to": message.to,
                "title": message.title,
                "body": message.body,
                "data": message.data,
            }
        ]
        try:
            with httpx.Client(
                timeout=self._timeout,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = client.post(self._url, json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return PushOutcome(status=PushStatus.FAILED, detail=str(exc))

        return _parse_tickets(body)


def _parse_tickets(body: object) -> PushOutcome:
    tickets = body.get("data") if isinstance(body, dict) else None
    if not isinstance(tickets, list) or not tickets:
        return PushOutcome(status=PushStatus.FAILED, detail="推送响应缺少 data")
    ticket = tickets[0]
    if not isinstance(ticket, dict):
        return PushOutcome(status=PushStatus.FAILED, detail="推送响应格式异常")
    if ticket.get("status") == "error":
        details = ticket.get("details")
        error_code = details.get("error") if isinstance(details, dict) else None
        if error_code == "DeviceNotRegistered":
            return PushOutcome(status=PushStatus.INVALID, detail="DeviceNotRegistered")
        message = ticket.get("message")
        return PushOutcome(
            status=PushStatus.FAILED,
            detail=str(message) if message is not None else "推送投递失败",
        )
    return PushOutcome(status=PushStatus.SENT)


class SkippedPushGateway(PushGateway):
    """推送关闭时使用；任何投递都记为跳过。"""

    def send(self, message: PushMessage) -> PushOutcome:
        return PushOutcome(status=PushStatus.SKIPPED, detail="推送未启用")

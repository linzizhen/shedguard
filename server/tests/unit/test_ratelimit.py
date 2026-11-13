"""令牌桶限流：突发上限、补充速率、key 清理与 key 生成。"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from shedguard_server.api.ratelimit import TokenBucketLimiter, client_key


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(
    *, per_minute: int = 2, burst: int = 2, stale_seconds: float = 300.0
) -> tuple[TokenBucketLimiter, FakeClock]:
    clock = FakeClock()
    limiter = TokenBucketLimiter(
        per_minute=per_minute,
        burst=burst,
        clock=clock,
        stale_seconds=stale_seconds,
    )
    return limiter, clock


def _request(*, host: str = "10.0.0.8", authorization: str | None = None) -> Request:
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/images",
        "raw_path": b"/api/v1/images",
        "query_string": b"",
        "headers": headers,
        "client": (host, 54321),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_burst_is_enforced() -> None:
    limiter, _ = _limiter(per_minute=2, burst=2)

    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]


def test_tokens_refill_at_configured_rate() -> None:
    limiter, clock = _limiter(per_minute=2, burst=2)

    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False

    clock.advance(30)  # 2/分钟 = 每 30 秒补一个
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False


def test_tokens_are_capped_by_burst() -> None:
    limiter, clock = _limiter(per_minute=2, burst=2)

    assert limiter.allow("a") is True
    clock.advance(600)  # 补满后仍然只能存 burst 个
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]


def test_old_keys_are_swept() -> None:
    limiter, clock = _limiter(stale_seconds=300)
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True
    assert limiter.size == 2

    clock.advance(301)
    assert limiter.allow("c") is True  # 触发清扫，a/b 都过期
    assert limiter.size == 1


def test_fresh_key_survives_sweep() -> None:
    limiter, clock = _limiter(stale_seconds=300)
    assert limiter.allow("old") is True
    clock.advance(200)
    assert limiter.allow("fresh") is True

    clock.advance(101)  # 距上次清扫已超过 60 秒，old 过期而 fresh 未过期
    assert limiter.allow("fresh") is True
    assert limiter.size == 1


def test_keys_are_independent() -> None:
    limiter, _ = _limiter(per_minute=2, burst=1)

    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True


@pytest.mark.parametrize(("per_minute", "burst"), [(0, 1), (-1, 1), (1, 0), (1, -2)])
def test_invalid_limits_are_rejected(per_minute: int, burst: int) -> None:
    with pytest.raises(ValueError):
        TokenBucketLimiter(per_minute=per_minute, burst=burst)


def test_client_key_combines_ip_and_token_digest() -> None:
    key = client_key(_request(host="10.0.0.8", authorization="Bearer abc"))
    host, digest = key.split("#")

    assert host == "10.0.0.8"
    assert len(digest) == 12
    assert digest != "Bearer abc"


def test_client_key_is_stable_for_same_token() -> None:
    first = client_key(_request(authorization="Bearer abc"))
    second = client_key(_request(authorization="Bearer abc"))

    assert first == second


def test_client_key_separates_tokens_and_hosts() -> None:
    first = client_key(_request(authorization="Bearer abc"))
    second = client_key(_request(authorization="Bearer xyz"))
    third = client_key(_request(host="10.0.0.9", authorization="Bearer abc"))

    assert len({first, second, third}) == 3


def test_client_key_marks_anonymous_calls() -> None:
    assert client_key(_request()).endswith("#anonymous")
    assert client_key(_request()).startswith("10.0.0.8#")
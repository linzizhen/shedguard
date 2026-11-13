"""请求速率限制：进程内令牌桶，按「客户端 IP + 令牌摘要」分组。

为什么用 `threading.Lock` 而不是 `asyncio.Lock`：

- 限流状态是进程级共享数据，不隶属某个事件循环；服务既可能在 uvicorn 的
  事件循环里调用，也可能在同步依赖的线程池、TestClient 的 portal 线程里
  调用，`threading.Lock` 对调用方线程没有亲和性要求。
- 临界区只有字典读写与浮点运算，没有 `await`，持锁时间是微秒级，即使偶尔
  阻塞事件循环也可以忽略；换成 `asyncio.Lock` 反而要求所有调用点都在协程里，
  并承担「锁属于哪个 loop」的额外复杂度。
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from starlette.requests import Request

# 健康检查、文档与 OpenAPI 是运维与调试入口，限流会掩盖真实故障。
EXEMPT_PATHS = frozenset({"/healthz", "/readyz", "/docs", "/openapi.json"})

# key 只保留 Authorization 摘要的前 12 位十六进制字符，避免把令牌写进内存键或日志。
AUTH_KEY_LENGTH = 12
ANONYMOUS_KEY = "anonymous"

# 长期未出现的 key 会被清理；每分钟至多扫描一次，均摊成本接近零。
DEFAULT_STALE_SECONDS = 300.0
SWEEP_INTERVAL_SECONDS = 60.0


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """按 key 维护令牌桶：容量 `burst`，每分钟匀速补充 `per_minute` 个令牌。"""

    def __init__(
        self,
        *,
        per_minute: int,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        stale_seconds: float = DEFAULT_STALE_SECONDS,
    ) -> None:
        if per_minute <= 0:
            raise ValueError("per_minute 必须为正数")
        if burst <= 0:
            raise ValueError("burst 必须为正数")
        self._rate_per_second = per_minute / 60.0
        self._burst = float(burst)
        self._clock = clock
        self._stale_seconds = stale_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_sweep = clock()

    @property
    def size(self) -> int:
        """当前跟踪的 key 数量；用于测试与运维观测。"""
        with self._lock:
            return len(self._buckets)

    def allow(self, key: str) -> bool:
        """取一个令牌；桶空时返回 False，不排队、不睡眠。"""
        now = self._clock()
        with self._lock:
            self._sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._burst, updated_at=now)
                self._buckets[key] = bucket
                refilled = self._burst
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                refilled = min(self._burst, bucket.tokens + elapsed * self._rate_per_second)
            allowed = refilled >= 1.0
            bucket.tokens = refilled - 1.0 if allowed else refilled
            bucket.updated_at = now
            return allowed

    def _sweep(self, now: float) -> None:
        """删除长期未出现的 key，避免内存随客户端数量无界增长。"""
        if now - self._last_sweep < SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        stale = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.updated_at >= self._stale_seconds
        ]
        for key in stale:
            del self._buckets[key]


def client_key(request: Request) -> str:
    """客户端 IP + Authorization 头哈希前 12 位；没有令牌时用固定占位。"""
    client = request.client
    host = client.host if client is not None else "unknown"
    authorization = request.headers.get("authorization")
    if not authorization:
        return f"{host}#{ANONYMOUS_KEY}"
    digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:AUTH_KEY_LENGTH]
    return f"{host}#{digest}"
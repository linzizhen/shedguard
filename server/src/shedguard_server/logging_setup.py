"""结构化日志：JSON 行格式，request_id 由 contextvars 贯穿一次请求。"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Literal, TextIO
from zoneinfo import ZoneInfo

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

DEFAULT_TIMEZONE = "Asia/Shanghai"


class JsonFormatter(logging.Formatter):
    """把 LogRecord 序列化为单行 JSON。"""

    def __init__(self, tz: ZoneInfo | None = None) -> None:
        super().__init__()
        self._tz = tz or ZoneInfo(DEFAULT_TIMEZONE)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=self._tz).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # 结构化日志走管道与文件，统一转义非 ASCII，避免 Windows 控制台编码不一致。
        return json.dumps(payload, ensure_ascii=True)


class ConsoleFormatter(logging.Formatter):
    """开发期可读格式，保留 request_id 便于对照。"""

    def __init__(self, tz: ZoneInfo | None = None) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        self._tz = tz or ZoneInfo(DEFAULT_TIMEZONE)

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get() or "-"
        return super().format(record)


def _ensure_utf8(stream: TextIO) -> TextIO:
    """Windows 下 stdout 默认按 GBK 编码，改成 UTF-8 以免中文日志乱码。"""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")
    return stream


def configure_logging(
    level: str = "INFO",
    fmt: Literal["json", "console"] = "json",
    tz: ZoneInfo | None = None,
) -> None:
    """安装一个受本模块管理的 stdout handler，重复调用不会叠加。"""
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        if getattr(handler, "_shedguard", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(_ensure_utf8(sys.stdout))
    handler._shedguard = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter(tz) if fmt == "json" else ConsoleFormatter(tz))
    root.addHandler(handler)
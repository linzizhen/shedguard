"""结构化日志：JSON 格式、request_id 注入与异常记录。"""

import json
import logging

from shedguard_server.logging_setup import (
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    request_id_var,
)


def _make_record(msg: str = "收到图片", level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="shedguard.test",
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_json_formatter_emits_required_fields() -> None:
    payload = json.loads(JsonFormatter().format(_make_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "shedguard.test"
    assert payload["msg"] == "收到图片"
    assert payload["request_id"] is None
    assert "ts" in payload
    assert payload["ts"].endswith("+08:00")


def test_request_id_is_injected_from_contextvar() -> None:
    token = request_id_var.set("req-abc")
    try:
        payload = json.loads(JsonFormatter().format(_make_record()))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-abc"


def test_exception_is_serialized() -> None:
    try:
        raise ValueError("坏字节")
    except ValueError:
        import sys

        record = _make_record(level=logging.ERROR)
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert "ValueError: 坏字节" in payload["exc"]


def test_console_formatter_shows_request_id_and_message() -> None:
    token = request_id_var.set("req-x")
    try:
        text = ConsoleFormatter().format(_make_record("启动中"))
    finally:
        request_id_var.reset(token)

    assert "req-x" in text
    assert "启动中" in text


def test_console_formatter_falls_back_to_dash_when_no_request_id() -> None:
    text = ConsoleFormatter().format(_make_record("启动中"))

    assert "[-]" in text


def test_configure_logging_is_idempotent_and_writes_json() -> None:
    configure_logging(level="INFO", fmt="json")
    configure_logging(level="INFO", fmt="json")

    root = logging.getLogger()
    handlers = [h for h in root.handlers if getattr(h, "_shedguard", False)]

    assert len(handlers) == 1
    assert handlers[0].formatter is not None
    assert isinstance(handlers[0].formatter, JsonFormatter)
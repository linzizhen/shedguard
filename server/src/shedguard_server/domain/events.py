"""蜕皮事件的领域校验。"""

from __future__ import annotations

from datetime import date

from shedguard_server.errors import InvalidRequestError

OUTCOMES = frozenset({"completed", "partial", "stuck", "unknown"})
MAX_NOTES_LENGTH = 2000


def validate_outcome(raw: str) -> str:
    """outcome 必须是四个已知状态之一，且不做宽松归一化。"""
    if raw not in OUTCOMES:
        msg = f"outcome 必须是 {sorted(OUTCOMES)} 之一，收到 {raw!r}"
        raise InvalidRequestError(msg)
    return raw


def validate_notes(raw: str | None) -> str | None:
    """备注去首尾空白；空白视为未填；长度不超过 2000 字符。"""
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    if len(trimmed) > MAX_NOTES_LENGTH:
        msg = f"notes 长度不能超过 {MAX_NOTES_LENGTH} 字符，收到 {len(trimmed)} 字符"
        raise InvalidRequestError(msg)
    return trimmed


def parse_event_date(raw: str) -> date:
    """严格解析 `YYYY-MM-DD`；带时间或非 ISO 格式一律拒绝。"""
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        msg = f"event_date 必须是 YYYY-MM-DD: {raw!r}"
        raise InvalidRequestError(msg) from exc
    if parsed.isoformat() != raw:
        # date.fromisoformat 接受 "20261105" 这类紧凑写法，这里收紧到标准形式。
        msg = f"event_date 必须是 YYYY-MM-DD: {raw!r}"
        raise InvalidRequestError(msg)
    return parsed
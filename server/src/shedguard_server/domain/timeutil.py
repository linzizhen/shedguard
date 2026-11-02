"""时区换算：入库时间统一 UTC，按配置时区派生本地日期分片。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def normalize_to_utc(moment: datetime) -> datetime:
    """无时区信息的时间按 UTC 解释，有时区信息的转换到 UTC。"""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def local_moment_of(moment_utc: datetime, tz: ZoneInfo) -> datetime:
    """把已带时区的时间换算到目标时区；无时区信息的时间视为编码错误。"""
    if moment_utc.tzinfo is None:
        msg = "时间必须携带时区信息"
        raise ValueError(msg)
    return moment_utc.astimezone(tz)


def local_date_of(moment_utc: datetime, tz: ZoneInfo) -> date:
    """返回该时刻在目标时区下的日期，用于按天分片。"""
    return local_moment_of(moment_utc, tz).date()


def parse_rfc3339(raw: str) -> datetime:
    """解析 RFC 3339 时间串并归一到 UTC；无法解析时抛 ValueError。"""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"无法解析的时间戳: {raw!r}"
        raise ValueError(msg) from exc
    return normalize_to_utc(parsed)
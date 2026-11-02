"""每日代表帧：把一天的多张图片收敛成一条可对比的帧。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from shedguard_server.domain.models import DailyFrame, ImageRecord

# 一次序列查询允许的最大天数，与接口约定一致。
MAX_SERIES_DAYS = 366


def _target_moment(local_day: date, capture_hour: int, tz: tzinfo) -> datetime:
    return datetime(local_day.year, local_day.month, local_day.day, capture_hour, tzinfo=tz)


def _distance_seconds(record: ImageRecord, target: datetime, tz: tzinfo) -> float:
    local_moment = record.captured_at_utc.astimezone(tz)
    return abs((local_moment - target).total_seconds())


def select_representative(
    candidates: Iterable[ImageRecord],
    *,
    local_day: date,
    tz: tzinfo,
    capture_hour: int,
    window_minutes: int,
) -> DailyFrame:
    """在一天的多张图片里选出代表帧。

    - 窗口内有图：取离目标时刻最近的一张，`in_window = True`。
    - 窗口内无图：取全天最近的一张，`in_window = False`，由消费方决定是否降级使用。
    - 全天无图：返回缺失帧。
    """
    records = list(candidates)
    target = _target_moment(local_day, capture_hour, tz)
    if not records:
        return DailyFrame(
            local_date=local_day,
            image_id=None,
            captured_at_utc=None,
            in_window=False,
            total_images=0,
        )

    window_seconds = window_minutes * 60
    scored = [
        (_distance_seconds(record, target, tz), record.captured_at_utc, record)
        for record in records
    ]
    inside = [item for item in scored if item[0] <= window_seconds]
    pool = inside or scored
    _, _, best = min(pool, key=lambda item: (item[0], item[1]))
    return DailyFrame(
        local_date=local_day,
        image_id=best.id,
        captured_at_utc=best.captured_at_utc,
        in_window=bool(inside),
        total_images=len(records),
    )


def build_daily_series(
    records: Iterable[ImageRecord],
    *,
    start: date,
    end: date,
    tz: tzinfo,
    capture_hour: int,
    window_minutes: int,
) -> list[DailyFrame]:
    """把区间内的记录铺成逐日序列，缺失日补空帧。"""
    if start > end:
        msg = f"起始日期不能晚于结束日期: {start} > {end}"
        raise ValueError(msg)
    span = (end - start).days + 1
    if span > MAX_SERIES_DAYS:
        msg = f"查询区间不能超过 {MAX_SERIES_DAYS} 天: 收到 {span} 天"
        raise ValueError(msg)

    grouped: dict[date, list[ImageRecord]] = {}
    for record in records:
        if start <= record.local_date <= end:
            grouped.setdefault(record.local_date, []).append(record)

    frames: list[DailyFrame] = []
    current = start
    while current <= end:
        frames.append(
            select_representative(
                grouped.get(current, ()),
                local_day=current,
                tz=tz,
                capture_hour=capture_hour,
                window_minutes=window_minutes,
            )
        )
        current += timedelta(days=1)
    return frames
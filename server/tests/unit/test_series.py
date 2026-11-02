"""每日代表帧选择规则：窗口内取最近、窗口外标注、缺失日补全。"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from shedguard_server.domain.models import ImageRecord
from shedguard_server.domain.series import build_daily_series, select_representative

TZ = ZoneInfo("Asia/Shanghai")


def _record(captured: datetime, *, local_day: date) -> ImageRecord:
    return ImageRecord(
        id=f"id-{captured.isoformat()}",
        device_id="cam-1",
        rel_path=f"images/{local_day.isoformat()}/cam-1/{captured:%H%M%S}.jpg",
        byte_size=10,
        sha256="0" * 64,
        captured_at_utc=captured,
        local_date=local_day,
        received_at_utc=captured,
    )


def _utc(hour: int, minute: int = 0, *, day: date = date(2026, 11, 1)) -> datetime:
    """本地 20:00 = UTC 12:00；这里按本地时刻反推 UTC。"""
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
    return local.astimezone(UTC)


def test_picks_only_candidate_in_window() -> None:
    day = date(2026, 11, 1)
    record = _record(_utc(20, 30), local_day=day)

    frame = select_representative(
        [record],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.image_id == record.id
    assert frame.in_window is True
    assert frame.total_images == 1


def test_picks_closest_within_window() -> None:
    day = date(2026, 11, 1)
    near = _record(_utc(20, 10), local_day=day)
    far = _record(_utc(21, 40), local_day=day)

    frame = select_representative(
        [far, near],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.image_id == near.id


def test_tie_prefers_earlier_capture() -> None:
    day = date(2026, 11, 1)
    earlier = _record(_utc(19, 0), local_day=day)
    later = _record(_utc(21, 0), local_day=day)

    frame = select_representative(
        [later, earlier],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.image_id == earlier.id


def test_falls_back_to_closest_outside_window_and_flags_it() -> None:
    day = date(2026, 11, 1)
    record = _record(_utc(11, 0), local_day=day)

    frame = select_representative(
        [record],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.image_id == record.id
    assert frame.in_window is False


def test_missing_day_yields_empty_frame() -> None:
    day = date(2026, 11, 1)

    frame = select_representative(
        [],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.image_id is None
    assert frame.captured_at_utc is None
    assert frame.in_window is False
    assert frame.total_images == 0


def test_window_boundary_is_inclusive() -> None:
    day = date(2026, 11, 1)
    record = _record(_utc(17, 0), local_day=day)

    frame = select_representative(
        [record],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert frame.in_window is True


def test_converts_to_local_timezone_before_comparing() -> None:
    """UTC 12:00 在 Asia/Shanghai 是 20:00，应当命中窗口中心。"""
    day = date(2026, 11, 1)
    record = _record(datetime(2026, 11, 1, 12, 0, tzinfo=UTC), local_day=day)

    frame = select_representative(
        [record],
        local_day=day,
        tz=TZ,
        capture_hour=20,
        window_minutes=0,
    )

    assert frame.in_window is True


def test_build_daily_series_fills_missing_days() -> None:
    start = date(2026, 11, 1)
    end = date(2026, 11, 3)
    first = _record(_utc(20, 5, day=date(2026, 11, 1)), local_day=date(2026, 11, 1))
    third = _record(_utc(20, 5, day=date(2026, 11, 3)), local_day=date(2026, 11, 3))

    frames = build_daily_series(
        [third, first],
        start=start,
        end=end,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert [frame.local_date for frame in frames] == [start, date(2026, 11, 2), end]
    assert frames[0].image_id == first.id
    assert frames[1].image_id is None
    assert frames[2].image_id == third.id


def test_build_daily_series_groups_by_local_date() -> None:
    start = date(2026, 11, 1)
    same_day = [
        _record(_utc(20, 0, day=start), local_day=start),
        _record(_utc(21, 0, day=start), local_day=start),
    ]

    frames = build_daily_series(
        same_day,
        start=start,
        end=start,
        tz=TZ,
        capture_hour=20,
        window_minutes=180,
    )

    assert len(frames) == 1
    assert frames[0].total_images == 2
    assert frames[0].image_id == same_day[0].id


def test_build_daily_series_rejects_reversed_range() -> None:
    with pytest.raises(ValueError, match="起始日期"):
        build_daily_series(
            [],
            start=date(2026, 11, 3),
            end=date(2026, 11, 1),
            tz=TZ,
            capture_hour=20,
            window_minutes=180,
        )


def test_build_daily_series_rejects_overlong_range() -> None:
    with pytest.raises(ValueError, match="366"):
        build_daily_series(
            [],
            start=date(2026, 1, 1),
            end=date(2026, 1, 1) + timedelta(days=366),
            tz=TZ,
            capture_hour=20,
            window_minutes=180,
        )
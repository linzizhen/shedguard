"""时区换算：入库时间统一 UTC，按配置时区派生本地日期分片。"""

from datetime import UTC, datetime

import pytest

from shedguard_server.domain.timeutil import local_date_of, local_moment_of, normalize_to_utc


def test_naive_datetime_is_treated_as_utc() -> None:
    assert normalize_to_utc(datetime(2026, 11, 2, 6, 30, 5)) == datetime(
        2026, 11, 2, 6, 30, 5, tzinfo=UTC
    )


def test_aware_datetime_is_converted_to_utc() -> None:
    from zoneinfo import ZoneInfo

    shanghai = datetime(2026, 11, 2, 14, 30, 5, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert normalize_to_utc(shanghai) == datetime(2026, 11, 2, 6, 30, 5, tzinfo=UTC)


def test_local_date_uses_configured_timezone() -> None:
    from zoneinfo import ZoneInfo

    shanghai = ZoneInfo("Asia/Shanghai")
    moment = datetime(2026, 11, 2, 16, 30, tzinfo=UTC)

    assert local_date_of(moment, shanghai).isoformat() == "2026-11-03"


def test_local_moment_matches_date_used_for_sharding() -> None:
    from zoneinfo import ZoneInfo

    shanghai = ZoneInfo("Asia/Shanghai")
    moment = datetime(2026, 11, 2, 6, 30, 5, tzinfo=UTC)

    local = local_moment_of(moment, shanghai)

    assert local.isoformat() == "2026-11-02T14:30:05+08:00"
    assert local_date_of(moment, shanghai) == local.date()


def test_local_date_of_rejects_naive_input() -> None:
    from zoneinfo import ZoneInfo

    with pytest.raises(ValueError, match="时区"):
        local_date_of(datetime(2026, 11, 2, 6, 30), ZoneInfo("Asia/Shanghai"))
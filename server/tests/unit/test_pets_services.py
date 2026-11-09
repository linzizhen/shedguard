"""周期预测与宠物服务的单元测试。"""

from __future__ import annotations

from datetime import date

from shedguard_server.domain.pets import ShedRecord
from shedguard_server.services.pets import predict_next_shed

TODAY = date(2026, 11, 9)


def _record(started: str, completed: str | None = None) -> ShedRecord:
    from datetime import UTC, datetime

    now = datetime(2026, 11, 9, tzinfo=UTC)
    return ShedRecord(
        id=f"r-{started}",
        pet_id="pet-1",
        started_on=date.fromisoformat(started),
        completed_on=date.fromisoformat(completed) if completed else None,
        notes=None,
        created_at_utc=now,
        updated_at_utc=now,
    )


class TestPredictNextShed:
    """predict_next_shed 的规则分支。"""

    def test_zero_records_is_not_predictable(self) -> None:
        result = predict_next_shed([], today=TODAY)
        assert result.predictable is False
        assert "0" in result.reason

    def test_two_completed_records_insufficient(self) -> None:
        records = [_record("2026-08-01", "2026-08-03"), _record("2026-09-01", "2026-09-04")]
        result = predict_next_shed(records, today=TODAY)
        assert result.predictable is False
        assert "至少需要 3 次" in result.reason

    def test_three_records_predictable(self) -> None:
        records = [
            _record("2026-07-01", "2026-07-03"),
            _record("2026-08-01", "2026-08-04"),
            _record("2026-09-01", "2026-09-03"),
        ]
        result = predict_next_shed(records, today=TODAY)
        assert result.predictable is False  # 窗口 10-02 已过 today=11-09
        # 换一个更近的 today 验证可预测分支
        recent = predict_next_shed(records, today=date(2026, 9, 15))
        assert recent.predictable is True
        assert recent.median_interval_days == 31
        assert recent.based_on_cycles == 2
        # 间隔 [31, 31] → MAD=0 → 窗口收窄为单日：09-01 + 31 = 10-02
        assert recent.next_window_start == date(2026, 10, 2)
        assert recent.next_window_end == date(2026, 10, 2)

    def test_incomplete_records_do_not_count(self) -> None:
        records = [
            _record("2026-07-01", "2026-07-03"),
            _record("2026-08-01", "2026-08-04"),
            _record("2026-09-01"),  # 进行中，不算完整周期
        ]
        result = predict_next_shed(records, today=TODAY)
        assert result.predictable is False

    def test_passed_window_suggests_recording(self) -> None:
        records = [
            _record("2026-01-01", "2026-01-03"),
            _record("2026-02-01", "2026-02-04"),
            _record("2026-03-01", "2026-03-03"),
        ]
        result = predict_next_shed(records, today=TODAY)
        assert result.predictable is False
        assert "已过" in result.reason

    def test_mixed_intervals_median(self) -> None:
        records = [
            _record("2026-08-01", "2026-08-03"),
            _record("2026-09-01", "2026-09-03"),
            _record("2026-10-05", "2026-10-08"),
            _record("2026-11-05", "2026-11-07"),
        ]
        result = predict_next_shed(records, today=TODAY)
        assert result.predictable is True
        # 间隔 31, 34, 31 → 中位 31
        assert result.median_interval_days == 31

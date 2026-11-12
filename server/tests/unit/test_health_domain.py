"""设备健康判定的单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shedguard_server.domain.alerts import (
    ALERT_KIND_DEVICE_SILENT,
    ALERT_KIND_NO_DETECTION,
)
from shedguard_server.domain.health import DeviceHealthInput, evaluate_device_health

TZ = "Asia/Shanghai"


def _data(
    *,
    now: datetime,
    last_upload_at: datetime | None,
    recent_detections: tuple[bool, ...] = (),
    start: int = 8,
    end: int = 20,
) -> DeviceHealthInput:
    return DeviceHealthInput(
        device_id="dev-1",
        now=now,
        last_upload_at=last_upload_at,
        recent_detections=recent_detections,
        capture_start_hour=start,
        capture_end_hour=end,
        timezone=TZ,
    )


class TestDeviceSilent:
    def test_silent_within_active_window(self) -> None:
        # 14:00 本地时间，活跃时段内；7 小时无上传。
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now - timedelta(hours=7))
        )
        assert [f.kind for f in findings] == [ALERT_KIND_DEVICE_SILENT]
        assert "7 小时" in findings[0].detail

    def test_no_alert_at_night(self) -> None:
        # 23:00 本地时间，不在活跃时段；超时也不报。
        now = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now - timedelta(hours=10))
        )
        assert findings == []

    def test_never_uploaded_is_ignored(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        assert evaluate_device_health(_data(now=now, last_upload_at=None)) == []

    def test_not_exceeded_threshold(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        assert (
            evaluate_device_health(
                _data(now=now, last_upload_at=now - timedelta(hours=3))
            )
            == []
        )


class TestNoDetection:
    def test_streak_triggers(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now, recent_detections=(False,) * 5)
        )
        assert [f.kind for f in findings] == [ALERT_KIND_NO_DETECTION]

    def test_short_history_does_not_trigger(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now, recent_detections=(False,) * 4)
        )
        assert findings == []

    def test_any_detection_resets(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        recent = (False, False, True, False, False)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now, recent_detections=recent)
        )
        assert findings == []

    def test_custom_streak_threshold(self) -> None:
        now = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
        findings = evaluate_device_health(
            _data(now=now, last_upload_at=now, recent_detections=(False,) * 3),
            no_detection_streak=3,
        )
        assert [f.kind for f in findings] == [ALERT_KIND_NO_DETECTION]

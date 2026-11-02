"""序列编排：把仓储记录交给领域规则，产出一段逐日序列。"""

from __future__ import annotations

from datetime import date, tzinfo

from shedguard_server.domain.models import DailyFrame
from shedguard_server.domain.series import build_daily_series
from shedguard_server.domain.validation import validate_device_id
from shedguard_server.errors import InvalidRequestError
from shedguard_server.infra.repository import ImageRepository


class SeriesService:
    """按设备与日期区间查询图片，并按固定拍摄时刻收敛成每日代表帧。"""

    def __init__(
        self,
        repository: ImageRepository,
        *,
        tz: tzinfo,
        capture_hour: int,
        window_minutes: int,
    ) -> None:
        self._repository = repository
        self._tz = tz
        self._capture_hour = capture_hour
        self._window_minutes = window_minutes

    def build(
        self,
        *,
        device_id_raw: str | None,
        start: date,
        end: date,
    ) -> list[DailyFrame]:
        device_id = validate_device_id(device_id_raw)
        records = self._repository.list_for_range(device_id, start, end)
        try:
            return build_daily_series(
                records,
                start=start,
                end=end,
                tz=self._tz,
                capture_hour=self._capture_hour,
                window_minutes=self._window_minutes,
            )
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
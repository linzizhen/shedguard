"""时序判定服务：把指标记录整理成逐日判定。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from shedguard_server.domain.judgement import (
    SIGNAL_NAMES,
    DayJudgement,
    JudgementState,
    MetricPoint,
    judge_series,
    validate_range,
)
from shedguard_server.domain.models import FrameMetric
from shedguard_server.domain.validation import validate_device_id
from shedguard_server.errors import InvalidRequestError
from shedguard_server.infra.repository import FrameMetricRepository


@dataclass(frozen=True, slots=True)
class SignalReport:
    """一次信号查询的结果。"""

    device_id: str
    start: date
    end: date
    days: tuple[DayJudgement, ...]
    alert_days: int
    current_state: JudgementState


def _values_of(metric: FrameMetric) -> dict[str, float] | None:
    """取出六项指标；任一项缺失或未检出时返回 None。"""
    if not metric.detected:
        return None
    pairs = (
        ("lightness_mean", metric.lightness_mean),
        ("lightness_std", metric.lightness_std),
        ("saturation_mean", metric.saturation_mean),
        ("high_light_ratio", metric.high_light_ratio),
        ("edge_density", metric.edge_density),
        ("color_entropy", metric.color_entropy),
    )
    values: dict[str, float] = {}
    for name, value in pairs:
        if value is None:
            return None
        values[name] = value
    return values


def _build_points(records: list[FrameMetric], start: date, end: date) -> list[MetricPoint]:
    """把稀疏记录补齐成逐日序列，缺图的日期用空点占位。"""
    by_date = {record.local_date: record for record in records}
    points: list[MetricPoint] = []
    cursor = start
    while cursor <= end:
        record = by_date.get(cursor)
        if record is None:
            points.append(MetricPoint(local_date=cursor, image_id=None, values=None))
        else:
            points.append(
                MetricPoint(
                    local_date=cursor,
                    image_id=record.image_id,
                    values=_values_of(record),
                )
            )
        cursor += timedelta(days=1)
    return points


class JudgementService:
    """按设备与区间计算逐日判定。"""

    def __init__(
        self,
        repository: FrameMetricRepository,
        *,
        baseline_days: int,
        min_samples: int,
        z_threshold: float,
        min_signals: int,
        consecutive_days: int,
    ) -> None:
        self._repository = repository
        self._baseline_days = baseline_days
        self._min_samples = min_samples
        self._z_threshold = z_threshold
        self._min_signals = min_signals
        self._consecutive_days = consecutive_days

    def signals(self, *, device_id_raw: str, start: date, end: date) -> SignalReport:
        """计算区间内每天的判定状态。

        基线窗口会越过区间左端向前取历史，否则查询「最近七天」永远样本不足。
        """
        device_id = validate_device_id(device_id_raw)
        try:
            validate_range(start, end)
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc

        history_start = start - timedelta(days=self._baseline_days)
        records = self._repository.list_for_device(device_id, history_start, end)
        points = _build_points(records, history_start, end)

        judgements = judge_series(
            points,
            baseline_days=self._baseline_days,
            min_samples=self._min_samples,
            z_threshold=self._z_threshold,
            min_signals=self._min_signals,
            consecutive_days=self._consecutive_days,
        )

        visible = tuple(item for item in judgements if item.local_date >= start)
        alert_days = sum(1 for item in visible if item.state is JudgementState.ALERT)
        current = visible[-1].state if visible else JudgementState.NORMAL

        return SignalReport(
            device_id=device_id,
            start=start,
            end=end,
            days=visible,
            alert_days=alert_days,
            current_state=current,
        )


#: 指标名列表，供路由层序列化时保持稳定顺序。
SIGNALS: tuple[str, ...] = SIGNAL_NAMES
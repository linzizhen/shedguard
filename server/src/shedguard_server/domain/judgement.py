"""蜕皮时序判定：把每日指标序列变成带状态的风险信号。

算法核心是稳健 Z 分数（中位数 + MAD），而不是均值 + 标准差。
蜕皮当天本身就是离群点，用它会把自己的标准差撑大，越接近蜕皮越难检出。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Final

#: 参与判定的六项指标，顺序固定，输出时按此顺序排列。
SIGNAL_NAMES: Final[tuple[str, ...]] = (
    "lightness_mean",
    "lightness_std",
    "saturation_mean",
    "high_light_ratio",
    "edge_density",
    "color_entropy",
)

#: 每项指标在蜕皮前兆中的预期方向。+1 表示升高，-1 表示降低。
#: 只认符合先验方向的越界，反向偏离不算命中——灯管变暗不该被当成蜕皮。
SIGNAL_DIRECTIONS: Final[dict[str, int]] = {
    "lightness_mean": 1,
    "lightness_std": 1,
    "saturation_mean": -1,
    "high_light_ratio": 1,
    "edge_density": 1,
    "color_entropy": -1,
}

#: 正态分布下 MAD 与标准差的换算系数，使 |z| >= 2 大致对应两个标准差。
MAD_SCALE: Final = 0.6745

#: 一次查询允许的最大跨度，与每日序列保持一致。
MAX_SIGNAL_DAYS: Final = 366


class JudgementState(StrEnum):
    """某一天的判定状态。"""

    INSUFFICIENT = "insufficient"
    NORMAL = "normal"
    WATCH = "watch"
    ALERT = "alert"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """序列中的一天。没有代表帧时 ``values`` 为 None。"""

    local_date: date
    image_id: str | None
    values: Mapping[str, float] | None


@dataclass(frozen=True, slots=True)
class DayJudgement:
    """一天的判定结果。"""

    local_date: date
    image_id: str | None
    metrics: Mapping[str, float] | None
    z_scores: Mapping[str, float] | None
    hits: tuple[str, ...]
    state: JudgementState
    baseline_samples: int


def median(values: Sequence[float]) -> float:
    """中位数。空序列抛 ValueError。"""
    if not values:
        raise ValueError("样本为空，无法计算中位数")
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def robust_scale(samples: Sequence[float]) -> float:
    """MAD 尺度；全同值时退化为平均绝对偏差；仍为零则返回 0。"""
    centre = median(samples)
    deviations = [abs(value - centre) for value in samples]
    scale = median(deviations)
    if scale > 0.0:
        return scale
    fallback = sum(deviations) / len(deviations)
    return max(fallback, 0.0)


def robust_z(value: float, samples: Sequence[float]) -> float:
    """单项指标的稳健 Z 分数。尺度为零时返回 0（该指标不参与命中）。"""
    if not samples:
        return 0.0
    centre = median(samples)
    scale = robust_scale(samples)
    if scale <= 0.0:
        return 0.0
    return MAD_SCALE * (value - centre) / scale


def z_scores(
    values: Mapping[str, float], history: Sequence[Mapping[str, float]]
) -> dict[str, float]:
    """对六项指标逐项计算稳健 Z 分数。历史中缺失的指标跳过。"""
    scores: dict[str, float] = {}
    for name in SIGNAL_NAMES:
        samples = [item[name] for item in history if name in item]
        if not samples:
            continue
        scores[name] = robust_z(values[name], samples)
    return scores


def detect_hits(scores: Mapping[str, float], *, threshold: float) -> tuple[str, ...]:
    """方向正确且幅度达到阈值的指标。"""
    hits: list[str] = []
    for name in SIGNAL_NAMES:
        score = scores.get(name)
        if score is None:
            continue
        if score * SIGNAL_DIRECTIONS[name] >= threshold:
            hits.append(name)
    return tuple(hits)


def validate_range(start: date, end: date) -> None:
    """区间合法性：起止顺序与最大跨度。"""
    if start > end:
        raise ValueError(f"起始日期不能晚于结束日期: {start} > {end}")
    if (end - start).days + 1 > MAX_SIGNAL_DAYS:
        raise ValueError(f"查询区间不能超过 {MAX_SIGNAL_DAYS} 天: {start} ~ {end}")


def judge_series(
    points: Sequence[MetricPoint],
    *,
    baseline_days: int,
    min_samples: int,
    z_threshold: float,
    min_signals: int,
    consecutive_days: int,
) -> list[DayJudgement]:
    """按时间顺序判定每一天。

    ``points`` 必须按日期升序，且覆盖区间内每一天（缺图日用 ``image_id=None`` 占位）。
    基线只取当天之前的样本，绝不使用未来数据。
    """
    judgements: list[DayJudgement] = []
    streak = 0

    for index, point in enumerate(points):
        if point.image_id is None or point.values is None:
            # 没有证据的日子：既不算命中，也不让连续性越过它继续累加。
            # 状态记 insufficient 而不是 normal —— 「无法判断」和「一切正常」是两回事。
            streak = 0
            judgements.append(
                DayJudgement(
                    local_date=point.local_date,
                    image_id=None,
                    metrics=None,
                    z_scores=None,
                    hits=(),
                    state=JudgementState.INSUFFICIENT,
                    baseline_samples=0,
                )
            )
            continue

        window_start = point.local_date - timedelta(days=baseline_days)
        history = [
            item.values
            for item in points[:index]
            if item.values is not None and window_start <= item.local_date < point.local_date
        ]

        if len(history) < min_samples:
            streak = 0
            judgements.append(
                DayJudgement(
                    local_date=point.local_date,
                    image_id=point.image_id,
                    metrics=point.values,
                    z_scores=None,
                    hits=(),
                    state=JudgementState.INSUFFICIENT,
                    baseline_samples=len(history),
                )
            )
            continue

        scores = z_scores(point.values, history)
        hits = detect_hits(scores, threshold=z_threshold)

        if len(hits) >= min_signals:
            streak += 1
        else:
            streak = 0

        if streak >= consecutive_days:
            state = JudgementState.ALERT
        elif streak >= 1:
            state = JudgementState.WATCH
        else:
            state = JudgementState.NORMAL

        judgements.append(
            DayJudgement(
                local_date=point.local_date,
                image_id=point.image_id,
                metrics=point.values,
                z_scores=scores,
                hits=hits,
                state=state,
                baseline_samples=len(history),
            )
        )

    return judgements
"""判定算法单元测试。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from shedguard_server.domain.judgement import (
    DayJudgement,
    JudgementState,
    MetricPoint,
    detect_hits,
    judge_series,
    median,
    robust_scale,
    robust_z,
    validate_range,
    z_scores,
)

BASE: dict[str, float] = {
    "lightness_mean": 40.0,
    "lightness_std": 8.0,
    "saturation_mean": 30.0,
    "high_light_ratio": 0.10,
    "edge_density": 0.20,
    "color_entropy": 3.0,
}

JITTER: dict[str, float] = {
    "lightness_mean": 1.0,
    "lightness_std": 0.5,
    "saturation_mean": 1.0,
    "high_light_ratio": 0.02,
    "edge_density": 0.02,
    "color_entropy": 0.2,
}

START = date(2026, 1, 1)


def _stable(index: int) -> dict[str, float]:
    """交替抖动，保证 MAD 非零且中位数等于基准值。"""
    sign = 1.0 if index % 2 == 0 else -1.0
    return {name: BASE[name] + sign * JITTER[name] for name in BASE}


def _series(days: int, bumps: dict[int, dict[str, float]] | None = None) -> list[MetricPoint]:
    """构造连续序列。``bumps[day_index]`` 表示当天在基准值上加的量。"""
    points: list[MetricPoint] = []
    for index in range(days):
        values = _stable(index)
        if bumps and index in bumps:
            for name, delta in bumps[index].items():
                values[name] = BASE[name] + delta
        points.append(
            MetricPoint(
                local_date=START + timedelta(days=index),
                image_id=f"img-{index:03d}",
                values=values,
            )
        )
    return points


def _judge(points: list[MetricPoint], *, min_samples: int = 7) -> list[DayJudgement]:
    return judge_series(
        points,
        baseline_days=14,
        min_samples=min_samples,
        z_threshold=2.0,
        min_signals=2,
        consecutive_days=2,
    )


# ---- 基础统计 ----


def test_median_odd() -> None:
    assert median([3.0, 1.0, 2.0]) == 2.0


def test_median_even() -> None:
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_median_rejects_empty() -> None:
    with pytest.raises(ValueError):
        median([])


def test_robust_scale_of_constant_series_is_zero() -> None:
    assert robust_scale([5.0, 5.0, 5.0, 5.0]) == 0.0


def test_robust_scale_falls_back_to_mean_absolute_deviation() -> None:
    # 三个相同 + 一个偏离：MAD 的中位数落在 0，需要退化到平均绝对偏差。
    samples = [10.0, 10.0, 10.0, 14.0]
    assert robust_scale(samples) == pytest.approx(1.0)


def test_robust_z_is_zero_when_scale_is_zero() -> None:
    assert robust_z(99.0, [5.0, 5.0, 5.0]) == 0.0


def test_robust_z_sign_follows_deviation() -> None:
    samples = [10.0, 12.0, 8.0, 10.0, 12.0, 8.0]
    assert robust_z(20.0, samples) > 0.0
    assert robust_z(0.0, samples) < 0.0


# ---- 方向性 ----


def test_hit_requires_matching_direction() -> None:
    scores = {"lightness_mean": 3.0, "saturation_mean": -3.0}
    hits = detect_hits(scores, threshold=2.0)
    assert "lightness_mean" in hits
    assert "saturation_mean" in hits


def test_brightness_drop_is_not_a_hit() -> None:
    hits = detect_hits({"lightness_mean": -5.0}, threshold=2.0)
    assert hits == ()


def test_saturation_rise_is_not_a_hit() -> None:
    # 饱和度升高意味着颜色更浓，与蜕皮前兆相反。
    hits = detect_hits({"saturation_mean": 5.0}, threshold=2.0)
    assert hits == ()


def test_z_scores_skips_missing_history_names() -> None:
    history = [{"lightness_mean": 10.0}, {"lightness_mean": 12.0}]
    scores = z_scores({"lightness_mean": 20.0, "edge_density": 0.5}, history)
    assert set(scores) == {"lightness_mean"}


# ---- 序列判定 ----


def test_insufficient_before_min_samples() -> None:
    points = _series(5)
    judgements = _judge(points, min_samples=7)
    assert all(item.state is JudgementState.INSUFFICIENT for item in judgements)
    assert all(item.hits == () for item in judgements)


def test_alert_after_two_consecutive_days() -> None:
    bumps = {
        15: {"lightness_mean": 6.0, "saturation_mean": -10.0},
        16: {"lightness_mean": 6.0, "saturation_mean": -10.0},
    }
    judgements = _judge(_series(20, bumps=bumps))

    assert judgements[15].state is JudgementState.WATCH
    assert judgements[15].hits == ("lightness_mean", "saturation_mean")
    assert judgements[16].state is JudgementState.ALERT


def test_single_signal_is_not_enough() -> None:
    # 只有一项指标越界时，即使连续多天也不升级。
    bumps = {day: {"lightness_mean": 6.0} for day in (15, 16, 17)}
    judgements = _judge(_series(20, bumps=bumps))

    assert judgements[15].hits == ("lightness_mean",)
    assert all(judgements[day].state is JudgementState.NORMAL for day in (15, 16, 17))


def test_watch_then_normal_when_bump_disappears() -> None:
    bumps = {15: {"lightness_mean": 6.0, "saturation_mean": -10.0}}
    judgements = _judge(_series(20, bumps=bumps))

    assert judgements[15].state is JudgementState.WATCH
    assert judgements[16].state is JudgementState.NORMAL


def test_two_signals_at_once_can_alert_immediately_after_streak() -> None:
    bumps = {
        15: {"lightness_mean": 6.0, "high_light_ratio": 0.10},
        16: {"lightness_mean": 6.0, "high_light_ratio": 0.10},
    }
    judgements = _judge(_series(20, bumps=bumps))

    assert len(judgements[15].hits) == 2
    assert judgements[15].state is JudgementState.WATCH
    assert judgements[16].state is JudgementState.ALERT


def test_missing_day_breaks_streak() -> None:
    # 第 15 天的异常值会进入第 17 天的基线窗口并把尺度撑大，所以第 17 天用更大的偏移。
    bumps = {
        15: {"lightness_mean": 6.0, "saturation_mean": -10.0},
        17: {"lightness_mean": 12.0, "saturation_mean": -15.0},
    }
    points = _series(20, bumps=bumps)
    points[16] = MetricPoint(local_date=points[16].local_date, image_id=None, values=None)

    judgements = _judge(points)

    assert judgements[15].state is JudgementState.WATCH
    # 缺图日既不算命中，也不会被当成「正常」——它根本没有可判断的证据。
    assert judgements[16].state is JudgementState.INSUFFICIENT
    assert judgements[16].image_id is None
    # 缺日清零后，第 17 天重新从 watch 开始，而不是直接 alert。
    assert judgements[17].state is JudgementState.WATCH


def test_future_data_does_not_change_past_judgements() -> None:
    plain = _series(20)
    with_future = _series(25, bumps={20: {"lightness_mean": 30.0}, 21: {"lightness_mean": 30.0}})

    left = _judge(plain)
    right = _judge(with_future[:20])

    for index in range(20):
        assert left[index].state is right[index].state
        assert left[index].hits == right[index].hits


def test_baseline_samples_counted() -> None:
    judgements = _judge(_series(20, bumps={15: {"lightness_mean": 6.0}}))
    # 第 15 天回看 14 天，落在窗口内的是第 1..14 天，共 14 个样本。
    assert judgements[15].baseline_samples == 14


# ---- 区间校验 ----


def test_validate_range_rejects_reversed() -> None:
    with pytest.raises(ValueError, match="起始日期不能晚于结束日期"):
        validate_range(date(2026, 2, 1), date(2026, 1, 1))


def test_validate_range_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="查询区间不能超过"):
        validate_range(date(2025, 1, 1), date(2026, 6, 1))


def test_validate_range_accepts_single_day() -> None:
    validate_range(START, START)
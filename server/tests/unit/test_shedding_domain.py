"""蜕皮状态领域逻辑的单元测试。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import (
    DailyState,
    ShedState,
    StatePrediction,
    aggregate,
    crop_box,
    crop_frame,
    derive_events,
    softmax,
)


def _frame(width: int = 40, height: int = 30) -> ImageFrame:
    return ImageFrame(
        width=width,
        height=height,
        rgb=np.zeros((height, width, 3), dtype=np.uint8),
    )


def _day(day_number: int, state: ShedState | None) -> DailyState:
    return DailyState(
        local_date=date(2026, 11, day_number),
        state=state,
        votes={},
        image_count=0 if state is None else 1,
    )


class TestAggregate:
    def test_ignores_unknown_votes(self) -> None:
        states = [ShedState.UNKNOWN, ShedState.NORMAL, ShedState.UNKNOWN]

        assert aggregate(states) is ShedState.NORMAL

    def test_takes_the_mode(self) -> None:
        states = [ShedState.OPAQUE, ShedState.OPAQUE, ShedState.NORMAL]

        assert aggregate(states) is ShedState.OPAQUE

    def test_tie_prefers_the_shedding_side(self) -> None:
        # 漏报一次蜕皮的代价高于让用户多看一眼，平票时向蜕皮倾斜。
        assert aggregate([ShedState.NORMAL, ShedState.SHEDDING]) is ShedState.SHEDDING
        assert aggregate([ShedState.NORMAL, ShedState.OPAQUE]) is ShedState.OPAQUE
        assert aggregate([ShedState.OPAQUE, ShedState.SHEDDING]) is ShedState.SHEDDING

    def test_all_unknown_means_no_state(self) -> None:
        assert aggregate([ShedState.UNKNOWN, ShedState.UNKNOWN]) is None

    def test_empty_means_no_state(self) -> None:
        assert aggregate([]) is None


class TestDeriveEvents:
    def test_normal_to_opaque_is_shed_started(self) -> None:
        days = [_day(1, ShedState.NORMAL), _day(2, ShedState.OPAQUE)]

        events = derive_events(days)

        assert len(events) == 1
        assert events[0].event_type == "shed_started"
        assert events[0].local_date == date(2026, 11, 2)
        assert events[0].previous is ShedState.NORMAL
        assert events[0].current is ShedState.OPAQUE

    def test_shedding_to_normal_is_shed_completed(self) -> None:
        days = [_day(1, ShedState.SHEDDING), _day(2, ShedState.NORMAL)]

        events = derive_events(days)

        assert len(events) == 1
        assert events[0].event_type == "shed_completed"

    def test_opaque_to_shedding_is_not_an_event(self) -> None:
        days = [_day(1, ShedState.OPAQUE), _day(2, ShedState.SHEDDING)]

        assert derive_events(days) == []

    def test_missing_day_does_not_break_the_sequence(self) -> None:
        # 缺一天图不代表蜕皮结束了，所以空日被跳过而不是打断。
        days = [
            _day(1, ShedState.NORMAL),
            _day(2, ShedState.OPAQUE),
            _day(3, None),
            _day(4, ShedState.NORMAL),
        ]

        events = derive_events(days)

        assert [item.event_type for item in events] == [
            "shed_started",
            "shed_completed",
        ]

    def test_leading_missing_days_do_not_emit_events(self) -> None:
        days = [_day(1, None), _day(2, ShedState.OPAQUE)]

        assert derive_events(days) == []

    def test_full_cycle(self) -> None:
        days = [
            _day(1, ShedState.NORMAL),
            _day(2, ShedState.OPAQUE),
            _day(3, ShedState.SHEDDING),
            _day(4, ShedState.NORMAL),
        ]

        events = derive_events(days)

        assert [item.event_type for item in events] == [
            "shed_started",
            "shed_completed",
        ]
        assert events[1].local_date == date(2026, 11, 4)


class TestCropBox:
    def test_expands_by_ratio(self) -> None:
        box = crop_box((100, 100, 200, 200), width=400, height=400, padding=0.1)

        assert box == (90, 90, 210, 210)

    def test_clamps_to_frame(self) -> None:
        box = crop_box((0, 0, 100, 100), width=400, height=400, padding=0.5)

        assert box == (0, 0, 150, 150)

    def test_clamps_right_and_bottom(self) -> None:
        box = crop_box((300, 300, 400, 400), width=400, height=400, padding=0.5)

        assert box == (250, 250, 400, 400)


class TestCropFrame:
    def test_returns_the_region(self) -> None:
        frame = _frame(width=40, height=30)

        cropped = crop_frame(frame, (5, 4, 25, 20))

        assert cropped.width == 20
        assert cropped.height == 16
        assert cropped.rgb.shape == (16, 20, 3)

    def test_rejects_empty_region(self) -> None:
        frame = _frame()

        with pytest.raises(ValueError, match="裁剪区域无效"):
            crop_frame(frame, (10, 10, 10, 20))


class TestStatePrediction:
    def test_accepts_a_normal_distribution(self) -> None:
        prediction = StatePrediction(
            state=ShedState.OPAQUE,
            confidence=0.7,
            probabilities={"normal": 0.2, "opaque": 0.7, "shedding": 0.1},
        )

        assert prediction.state is ShedState.OPAQUE

    def test_rejects_unknown_as_a_classifier_output(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            StatePrediction(
                state=ShedState.UNKNOWN,
                confidence=0.5,
                probabilities={"normal": 0.5, "unknown": 0.5},
            )

    def test_rejects_confidence_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="置信度"):
            StatePrediction(
                state=ShedState.NORMAL,
                confidence=1.5,
                probabilities={"normal": 1.0},
            )

    def test_rejects_probabilities_not_summing_to_one(self) -> None:
        with pytest.raises(ValueError, match="概率之和"):
            StatePrediction(
                state=ShedState.NORMAL,
                confidence=0.5,
                probabilities={"normal": 0.5, "opaque": 0.2},
            )

    def test_rejects_empty_probabilities(self) -> None:
        with pytest.raises(ValueError, match="概率分布"):
            StatePrediction(state=ShedState.NORMAL, confidence=0.5, probabilities={})


class TestSoftmax:
    def test_sums_to_one(self) -> None:
        result = softmax(np.array([1.0, 2.0, 3.0], dtype=np.float32))

        assert float(np.sum(result)) == pytest.approx(1.0, abs=1e-5)

    def test_preserves_order(self) -> None:
        result = softmax(np.array([0.1, 5.0, 0.2], dtype=np.float32))

        assert int(np.argmax(result)) == 1

    def test_is_stable_for_large_logits(self) -> None:
        result = softmax(np.array([1000.0, 1001.0], dtype=np.float32))

        assert float(np.sum(result)) == pytest.approx(1.0, abs=1e-5)

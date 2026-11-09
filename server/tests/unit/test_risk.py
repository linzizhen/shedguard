"""卡皮风险评估规则引擎的单元测试。"""

from __future__ import annotations

import pytest

from shedguard_server.domain.risk import (
    EYE_VET_WARNING,
    RiskLevel,
    assess_stuck_shed_risk,
)


def _answers(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "last_shed_complete": "complete",
        "eye_condition": "clear",
        "toe_condition": "normal",
        "hydration": "daily",
        "humidity": "above_50",
        "water_bowl": "fresh_daily",
    }
    base.update(overrides)
    return base


class TestAssessStuckShedRisk:
    """规则分支与阈值边界。"""

    def test_all_healthy_is_low(self) -> None:
        result = assess_stuck_shed_risk(_answers())
        assert result.score == 0
        assert result.level == RiskLevel.LOW
        assert result.factors == ()
        assert result.vet_warning is None

    def test_stale_water_alone_is_low(self) -> None:
        result = assess_stuck_shed_risk(_answers(water_bowl="stale_or_absent"))
        assert result.score == 1
        assert result.level == RiskLevel.LOW

    def test_partial_body_retained(self) -> None:
        result = assess_stuck_shed_risk(_answers(last_shed_complete="partial_body"))
        assert result.score == 3
        assert result.level == RiskLevel.MODERATE
        assert result.factors[0]["key"] == "last_shed_complete"

    def test_large_retained_same_as_partial(self) -> None:
        result = assess_stuck_shed_risk(_answers(last_shed_complete="large_retained"))
        assert result.score == 3

    def test_retained_spectacle_triggers_vet_warning(self) -> None:
        result = assess_stuck_shed_risk(_answers(eye_condition="retained_spectacle"))
        assert result.score == 3
        assert result.vet_warning == EYE_VET_WARNING

    def test_swollen_toe(self) -> None:
        result = assess_stuck_shed_risk(_answers(toe_condition="swollen"))
        assert result.score == 3

    def test_discolored_toe(self) -> None:
        result = assess_stuck_shed_risk(_answers(toe_condition="discolored"))
        assert result.score == 2

    def test_hydration_levels(self) -> None:
        never = assess_stuck_shed_risk(_answers(hydration="rarely_never"))
        occasional = assess_stuck_shed_risk(_answers(hydration="occasional"))
        assert never.score == 2
        assert occasional.score == 1

    def test_low_humidity(self) -> None:
        result = assess_stuck_shed_risk(_answers(humidity="below_30_unknown"))
        assert result.score == 1
        assert result.level == RiskLevel.LOW

    def test_worst_case_is_high(self) -> None:
        result = assess_stuck_shed_risk(
            _answers(
                last_shed_complete="large_retained",
                eye_condition="retained_spectacle",
                toe_condition="swollen",
                hydration="rarely_never",
                humidity="below_30_unknown",
                water_bowl="stale_or_absent",
            )
        )
        assert result.score == 13
        assert result.level == RiskLevel.HIGH
        assert result.vet_warning == EYE_VET_WARNING
        assert len(result.factors) == 6

    def test_moderate_boundary_at_4(self) -> None:
        result = assess_stuck_shed_risk(
            _answers(
                toe_condition="swollen",
                hydration="occasional",
            )
        )
        assert result.score == 4
        assert result.level == RiskLevel.MODERATE

    def test_high_boundary_at_5(self) -> None:
        result = assess_stuck_shed_risk(
            _answers(
                toe_condition="swollen",
                hydration="rarely_never",
            )
        )
        assert result.score == 5
        assert result.level == RiskLevel.HIGH

    def test_invalid_answer_raises(self) -> None:
        with pytest.raises(ValueError, match="last_shed_complete"):
            assess_stuck_shed_risk(_answers(last_shed_complete="nonsense"))

    def test_missing_answer_raises(self) -> None:
        answers = _answers()
        del answers["eye_condition"]
        with pytest.raises(ValueError, match="eye_condition"):
            assess_stuck_shed_risk(answers)

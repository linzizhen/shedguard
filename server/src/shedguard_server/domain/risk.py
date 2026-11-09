"""卡皮（残留蜕皮）风险评估：规则引擎，不走模型。

分数来源与阈值在规格 4.5 节定义：0–1 低风险，2–4 中风险，≥5 高风险。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

EYE_VET_WARNING = "眼睛残留蜕皮必须由爬宠医生处理，自行操作有致盲风险"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """一次风险评估的结论。"""

    score: int
    level: RiskLevel
    factors: tuple[dict[str, Any], ...]
    vet_warning: str | None


def _check_enum(raw: Any, name: str, allowed: tuple[str, ...]) -> str:
    if raw not in allowed:
        allowed_text = "、".join(allowed)
        raise ValueError(f"{name} 必须是 {allowed_text} 之一")
    return str(raw)


def assess_stuck_shed_risk(answers: dict[str, Any]) -> RiskAssessment:
    """根据六题问卷计算卡皮风险。

    输入键（全部必填）：
    - last_shed_complete: "complete" | "partial_body" | "large_retained"
    - eye_condition: "clear" | "retained_spectacle"
    - toe_condition: "normal" | "swollen" | "discolored"
    - hydration: "daily" | "occasional" | "rarely_never"
    - humidity: "above_50" | "30_50" | "below_30_unknown"
    - water_bowl: "fresh_daily" | "stale_or_absent"
    """
    last_shed = _check_enum(
        answers.get("last_shed_complete"),
        "last_shed_complete",
        ("complete", "partial_body", "large_retained"),
    )
    eye = _check_enum(
        answers.get("eye_condition"),
        "eye_condition",
        ("clear", "retained_spectacle"),
    )
    toe = _check_enum(
        answers.get("toe_condition"), "toe_condition", ("normal", "swollen", "discolored")
    )
    hydration = _check_enum(
        answers.get("hydration"), "hydration", ("daily", "occasional", "rarely_never")
    )
    humidity = _check_enum(
        answers.get("humidity"), "humidity", ("above_50", "30_50", "below_30_unknown")
    )
    water = _check_enum(
        answers.get("water_bowl"), "water_bowl", ("fresh_daily", "stale_or_absent")
    )

    score = 0
    factors: list[dict[str, Any]] = []
    vet_warning: str | None = None

    if last_shed == "partial_body":
        score += 3
        factors.append({"key": "last_shed_complete", "points": 3, "detail": "身体有部分残留蜕皮"})
    elif last_shed == "large_retained":
        score += 3
        factors.append({"key": "last_shed_complete", "points": 3, "detail": "大面积残留蜕皮"})

    if eye == "retained_spectacle":
        score += 3
        factors.append(
            {
                "key": "eye_condition",
                "points": 3,
                "detail": "眼睛有残留的透明鳞片（retained spectacle）",
            }
        )
        vet_warning = EYE_VET_WARNING

    if toe == "swollen":
        score += 3
        factors.append({"key": "toe_condition", "points": 3, "detail": "脚趾红肿或不再抓握"})
    elif toe == "discolored":
        score += 2
        factors.append({"key": "toe_condition", "points": 2, "detail": "趾尖发黑或变色"})

    if hydration == "rarely_never":
        score += 2
        factors.append({"key": "hydration", "points": 2, "detail": "很少或从不提供加湿与饮水观察"})
    elif hydration == "occasional":
        score += 1
        factors.append({"key": "hydration", "points": 1, "detail": "偶尔加湿"})

    if humidity == "below_30_unknown":
        score += 1
        factors.append({"key": "humidity", "points": 1, "detail": "湿度低于 30% 或不确定"})

    if water == "stale_or_absent":
        score += 1
        factors.append({"key": "water_bowl", "points": 1, "detail": "水盆不新鲜或缺失"})

    if score <= 1:
        level = RiskLevel.LOW
    elif score <= 4:
        level = RiskLevel.MODERATE
    else:
        level = RiskLevel.HIGH

    return RiskAssessment(
        score=score,
        level=level,
        factors=tuple(factors),
        vet_warning=vet_warning,
    )

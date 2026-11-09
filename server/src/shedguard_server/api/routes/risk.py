"""卡皮风险评估接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shedguard_server.domain.risk import assess_stuck_shed_risk
from shedguard_server.errors import InvalidRequestError

router = APIRouter(prefix="/api/v1/risk-assessment", tags=["risk"])


class RiskAnswers(BaseModel):
    """六题问卷的请求体；全部必填。"""

    last_shed_complete: Literal["complete", "partial_body", "large_retained"]
    eye_condition: Literal["clear", "retained_spectacle"]
    toe_condition: Literal["normal", "swollen", "discolored"]
    hydration: Literal["daily", "occasional", "rarely_never"]
    humidity: Literal["above_50", "30_50", "below_30_unknown"]
    water_bowl: Literal["fresh_daily", "stale_or_absent"]


@router.post("")
async def assess_risk(body: RiskAnswers) -> JSONResponse:
    """根据问卷答案计算卡皮风险；纯规则引擎，不依赖模型。"""
    try:
        result = await run_in_threadpool(assess_stuck_shed_risk, body.model_dump())
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return JSONResponse(
        {
            "score": result.score,
            "level": result.level.value,
            "factors": [dict(f) for f in result.factors],
            "vet_warning": result.vet_warning,
        }
    )

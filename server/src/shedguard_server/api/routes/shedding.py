"""蜕皮状态识别路由：单图分类与按日聚合。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from shedguard_server.api.dependencies import (
    get_detector,
    get_image_repository,
    get_settings,
    get_shedding_state_repository,
    get_state_classifier,
    get_storage,
)
from shedguard_server.api.params import parse_day
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.models import SheddingState
from shedguard_server.domain.shedding import DailyState, ShedState, StateClassifier
from shedguard_server.infra.repository import ImageRepository, SheddingStateRepository
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.shedding import SheddingReport, SheddingService

router = APIRouter(prefix="/api/v1/shedding", tags=["shedding"])
series_router = APIRouter(prefix="/api/v1/series", tags=["series"])

#: 浮点输出的小数位数。
DECIMAL_PLACES = 4


def get_shedding_service(
    images: Annotated[ImageRepository, Depends(get_image_repository)],
    states: Annotated[SheddingStateRepository, Depends(get_shedding_state_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    detector: Annotated[Detector, Depends(get_detector)],
    classifier: Annotated[StateClassifier | None, Depends(get_state_classifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SheddingService:
    return SheddingService(
        images,
        states,
        storage,
        detector,
        classifier,
        min_confidence=settings.state_min_confidence,
        crop_padding=settings.state_crop_padding,
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMAL_PLACES)


def _round_map(values: dict[str, float] | None) -> dict[str, float] | None:
    if values is None:
        return None
    return {name: round(value, DECIMAL_PLACES) for name, value in values.items()}


def serialize_state(state: SheddingState) -> dict[str, Any]:
    return {
        "image_id": state.image_id,
        "device_id": state.device_id,
        "local_date": state.local_date.isoformat(),
        "state": state.state,
        "confidence": _round(state.confidence),
        "probabilities": _round_map(state.probabilities),
        "detector_name": state.detector_name,
        "classifier_name": state.classifier_name,
        "box": list(state.box) if state.box is not None else None,
        "computed_at_utc": state.computed_at_utc.isoformat(),
        "state_version": state.state_version,
    }


@router.post("/{image_id}", status_code=200)
async def classify_image(
    image_id: str,
    service: Annotated[SheddingService, Depends(get_shedding_service)],
) -> JSONResponse:
    """对单张图判定蜕皮状态；同一张图重复调用会直接返回已有结果。"""
    state = await run_in_threadpool(service.analyze, image_id)
    return JSONResponse(serialize_state(state))


def _serialize_day(day: DailyState) -> dict[str, Any]:
    return {
        "date": day.local_date.isoformat(),
        "state": day.state.value if day.state is not None else None,
        "votes": dict(day.votes),
        "image_count": day.image_count,
    }


def _serialize_report(report: SheddingReport) -> dict[str, Any]:
    return {
        "device_id": report.device_id,
        "from": report.start.isoformat(),
        "to": report.end.isoformat(),
        "days": [_serialize_day(day) for day in report.days],
        "events": [
            {
                "type": event.event_type,
                "date": event.local_date.isoformat(),
                "previous": event.previous.value,
                "current": event.current.value,
            }
            for event in report.events
        ],
        "current_state": (
            report.current_state.value if report.current_state is not None else None
        ),
    }


@series_router.get("/{device_id}/shedding")
def get_shedding_series(
    service: Annotated[SheddingService, Depends(get_shedding_service)],
    device_id: str,
    from_date: Annotated[str, Query(alias="from")],
    to_date: Annotated[str, Query(alias="to")],
) -> dict[str, Any]:
    """按设备与日期区间返回每日状态与推导出的蜕皮事件。"""
    start = parse_day(from_date, "from")
    end = parse_day(to_date, "to")
    report = service.series(device_id_raw=device_id, start=start, end=end)
    return _serialize_report(report)


#: 供文档与测试引用的状态枚举。
STATES: tuple[ShedState, ...] = tuple(ShedState)

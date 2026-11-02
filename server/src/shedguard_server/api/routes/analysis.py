"""体表信号分析路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from shedguard_server.api.dependencies import (
    get_detector,
    get_image_repository,
    get_metric_repository,
    get_settings,
    get_storage,
)
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.models import FrameMetric
from shedguard_server.infra.repository import FrameMetricRepository, ImageRepository
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.analysis import AnalysisService

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

DECIMAL_PLACES = 4


def get_analysis_service(
    images: Annotated[ImageRepository, Depends(get_image_repository)],
    metrics: Annotated[FrameMetricRepository, Depends(get_metric_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    detector: Annotated[Detector, Depends(get_detector)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisService:
    return AnalysisService(
        images,
        metrics,
        storage,
        detector,
        background_days=settings.background_days,
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMAL_PLACES)


def serialize_metric(metric: FrameMetric) -> dict[str, object]:
    return {
        "image_id": metric.image_id,
        "device_id": metric.device_id,
        "local_date": metric.local_date.isoformat(),
        "detected": metric.detected,
        "box": list(metric.box) if metric.box is not None else None,
        "detector_name": metric.detector_name,
        "detector_confidence": _round(metric.detector_confidence),
        "normalized": metric.normalized,
        "exposure_scale": _round(metric.exposure_scale),
        "lightness_mean": _round(metric.lightness_mean),
        "lightness_std": _round(metric.lightness_std),
        "saturation_mean": _round(metric.saturation_mean),
        "high_light_ratio": _round(metric.high_light_ratio),
        "edge_density": _round(metric.edge_density),
        "color_entropy": _round(metric.color_entropy),
        "background_lightness": _round(metric.background_lightness),
        "computed_at_utc": metric.computed_at_utc.isoformat(),
        "metrics_version": metric.metrics_version,
    }


@router.post("/{image_id}", status_code=200)
async def analyze_image(
    image_id: str,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> JSONResponse:
    """对单张图执行定位与信号提取；同一张图重复调用会直接返回已有结果。"""
    metric = await run_in_threadpool(service.analyze, image_id)
    return JSONResponse(serialize_metric(metric))
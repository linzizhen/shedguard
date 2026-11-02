"""序列接口：按设备与日期区间返回每日代表帧与判定信号。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from shedguard_server.api.dependencies import (
    get_image_repository,
    get_judgement_service,
    get_settings,
)
from shedguard_server.config import Settings
from shedguard_server.domain.judgement import DayJudgement
from shedguard_server.domain.models import DailyFrame
from shedguard_server.errors import InvalidRequestError
from shedguard_server.infra.repository import ImageRepository
from shedguard_server.services.judgement import JudgementService, SignalReport
from shedguard_server.services.series import SeriesService

router = APIRouter(prefix="/api/v1/series", tags=["series"])

#: 浮点指标输出的小数位数。
DECIMAL_PLACES = 4


def get_series_service(
    repository: Annotated[ImageRepository, Depends(get_image_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SeriesService:
    return SeriesService(
        repository,
        tz=settings.tzinfo,
        capture_hour=settings.capture_hour,
        window_minutes=settings.capture_window_minutes,
    )


def _parse_day(raw: str, name: str) -> date:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}") from exc
    if parsed.isoformat() != raw:
        raise InvalidRequestError(f"{name} 必须是 YYYY-MM-DD: {raw!r}")
    return parsed


def _serialize_frame(frame: DailyFrame) -> dict[str, Any]:
    captured = frame.captured_at_utc
    return {
        "date": frame.local_date.isoformat(),
        "image_id": frame.image_id,
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z") if captured else None,
        "in_window": frame.in_window,
        "total_images": frame.total_images,
    }


@router.get("")
def get_series(
    service: Annotated[SeriesService, Depends(get_series_service)],
    device_id: Annotated[str, Query(min_length=1)],
    from_date: Annotated[str, Query(alias="from")],
    to_date: Annotated[str, Query(alias="to")],
) -> dict[str, Any]:
    start = _parse_day(from_date, "from")
    end = _parse_day(to_date, "to")
    frames = service.build(device_id_raw=device_id, start=start, end=end)
    return {
        "device_id": device_id,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days": [_serialize_frame(frame) for frame in frames],
        "total_days": len(frames),
        "missing_days": sum(1 for frame in frames if frame.image_id is None),
    }


def _round_metrics(values: dict[str, float] | None) -> dict[str, float] | None:
    if values is None:
        return None
    return {name: round(value, DECIMAL_PLACES) for name, value in values.items()}


def _serialize_judgement(item: DayJudgement) -> dict[str, Any]:
    return {
        "date": item.local_date.isoformat(),
        "image_id": item.image_id,
        "metrics": _round_metrics(dict(item.metrics) if item.metrics is not None else None),
        "z_scores": _round_metrics(dict(item.z_scores) if item.z_scores is not None else None),
        "hits": list(item.hits),
        "state": item.state.value,
        "baseline_samples": item.baseline_samples,
    }


def _serialize_report(report: SignalReport) -> dict[str, Any]:
    return {
        "device_id": report.device_id,
        "from": report.start.isoformat(),
        "to": report.end.isoformat(),
        "days": [_serialize_judgement(item) for item in report.days],
        "alert_days": report.alert_days,
        "current_state": report.current_state.value,
    }


@router.get("/{device_id}/signals")
def get_signals(
    service: Annotated[JudgementService, Depends(get_judgement_service)],
    device_id: str,
    from_date: Annotated[str, Query(alias="from")],
    to_date: Annotated[str, Query(alias="to")],
) -> dict[str, Any]:
    start = _parse_day(from_date, "from")
    end = _parse_day(to_date, "to")
    report = service.signals(device_id_raw=device_id, start=start, end=end)
    return _serialize_report(report)
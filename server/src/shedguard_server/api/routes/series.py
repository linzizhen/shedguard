"""序列接口：按设备与日期区间返回每日代表帧。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from shedguard_server.api.dependencies import get_image_repository, get_settings
from shedguard_server.config import Settings
from shedguard_server.domain.models import DailyFrame
from shedguard_server.errors import InvalidRequestError
from shedguard_server.infra.repository import ImageRepository
from shedguard_server.services.series import SeriesService

router = APIRouter(prefix="/api/v1/series", tags=["series"])


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
"""萌照接口：列表、今日、反馈、设置与成品图。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from shedguard_server.api.dependencies import (
    get_current_user,
    get_image_repository,
    get_metric_repository,
    get_pet_repository,
    get_portrait_feedback_repository,
    get_portrait_setting_repository,
    get_portrait_shot_repository,
    get_push_device_repository,
    get_settings,
    get_storage,
    get_user_repository,
)
from shedguard_server.config import Settings
from shedguard_server.domain.portrait import PortraitSetting, PortraitShot
from shedguard_server.domain.user import User
from shedguard_server.errors import UnauthorizedError
from shedguard_server.infra.auth import hash_token
from shedguard_server.infra.repository import (
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    PortraitFeedbackRepository,
    PortraitSettingRepository,
    PortraitShotRepository,
    PushDeviceRepository,
    UserRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.portraits import PortraitService

router = APIRouter(prefix="/api/v1", tags=["portraits"])


class PortraitSettingsUpdate(BaseModel):
    """萌照设置的部分更新；只填要改的字段。"""

    enabled: bool | None = None
    per_day: int | None = Field(default=None, ge=0, le=6)
    start_hour: int | None = Field(default=None, ge=0, le=23)
    end_hour: int | None = Field(default=None, ge=1, le=24)


class PortraitFeedbackCreate(BaseModel):
    """对一张萌照的反馈；`crop_head` 需要带人工框。"""

    kind: str = Field(min_length=1, max_length=16)
    crop_box: list[int] | None = Field(default=None, min_length=4, max_length=4)


def get_portrait_service(
    portraits: Annotated[PortraitShotRepository, Depends(get_portrait_shot_repository)],
    feedback: Annotated[
        PortraitFeedbackRepository, Depends(get_portrait_feedback_repository)
    ],
    settings_repo: Annotated[
        PortraitSettingRepository, Depends(get_portrait_setting_repository)
    ],
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    devices: Annotated[PushDeviceRepository, Depends(get_push_device_repository)],
    images: Annotated[ImageRepository, Depends(get_image_repository)],
    metrics: Annotated[FrameMetricRepository, Depends(get_metric_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PortraitService:
    return PortraitService(
        portraits=portraits,
        feedback=feedback,
        settings=settings_repo,
        pets=pets,
        devices=devices,
        images=images,
        metrics=metrics,
        storage=storage,
        output_px=settings.portrait_max_output_px,
        jpeg_quality=settings.portrait_jpeg_quality,
        min_subject_ratio=settings.portrait_min_subject_ratio,
        min_confidence=settings.portrait_min_detector_confidence,
        timezone=settings.timezone,
    )


def serialize_shot(shot: PortraitShot) -> dict[str, Any]:
    return {
        "id": shot.id,
        "device_id": shot.device_id,
        "pet_id": shot.pet_id,
        "local_date": shot.local_date.isoformat(),
        "slot": shot.slot,
        "source_image_id": shot.source_image_id,
        "width": shot.width,
        "height": shot.height,
        "score": round(shot.score, 4),
        "created_at_utc": shot.created_at_utc.isoformat(),
    }


def serialize_setting(setting: PortraitSetting) -> dict[str, Any]:
    return {
        "pet_id": setting.pet_id,
        "enabled": setting.enabled,
        "per_day": setting.per_day,
        "start_hour": setting.start_hour,
        "end_hour": setting.end_hour,
        "updated_at_utc": setting.updated_at_utc.isoformat(),
    }


@router.get("/pets/{pet_id}/portraits")
def list_portraits(
    pet_id: str,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    user: Annotated[User, Depends(get_current_user)],
    day: Annotated[date | None, Query(description="只看某一天")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    items = service.list_for_pet(pet_id, owner_id=user.id, local_date=day, limit=limit)
    return {"items": [serialize_shot(shot) for shot in items]}


@router.get("/pets/{pet_id}/portraits/today")
def today_portraits(
    pet_id: str,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    items = service.today(pet_id, owner_id=user.id)
    return {"items": [serialize_shot(shot) for shot in items]}


@router.get("/pets/{pet_id}/portrait-settings")
def get_portrait_settings(
    pet_id: str,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return serialize_setting(service.get_settings(pet_id, owner_id=user.id))


@router.put("/pets/{pet_id}/portrait-settings")
def update_portrait_settings(
    pet_id: str,
    payload: PortraitSettingsUpdate,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    updated = service.update_settings(
        pet_id,
        owner_id=user.id,
        enabled=payload.enabled,
        per_day=payload.per_day,
        start_hour=payload.start_hour,
        end_hour=payload.end_hour,
    )
    return serialize_setting(updated)


@router.post("/portraits/{shot_id}/feedback")
def create_portrait_feedback(
    shot_id: str,
    payload: PortraitFeedbackCreate,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    box = tuple(payload.crop_box) if payload.crop_box is not None else None
    feedback = service.add_feedback(
        shot_id,
        owner_id=user.id,
        kind=payload.kind,
        crop_box=box,  # type: ignore[arg-type]
    )
    return JSONResponse(
        {
            "id": feedback.id,
            "shot_id": feedback.shot_id,
            "kind": feedback.kind,
            "crop_box": list(feedback.crop_box) if feedback.crop_box else None,
            "created_at_utc": feedback.created_at_utc.isoformat(),
        },
        status_code=201,
    )


@router.get("/portraits/{shot_id}/image")
def get_portrait_image(
    shot_id: str,
    request: Request,
    service: Annotated[PortraitService, Depends(get_portrait_service)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    # 与图片一致：<Image> 组件不能加请求头，允许用查询参数传令牌。
    owner_id: str | None = None
    if settings.auth_enabled:
        raw = request.query_params.get("token", "")
        if not raw:
            scheme, _, credential = request.headers.get("authorization", "").partition(" ")
            raw = credential.strip() if scheme.lower() == "bearer" else ""
        resolved = users.find_by_token_hash(hash_token(raw)) if raw else None
        if resolved is None:
            raise UnauthorizedError("需要访问令牌")
        owner_id = resolved.id
    payload = service.read_image(shot_id, owner_id=owner_id)
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={"Cache-Control": "immutable"},
    )
"""数据贡献接口：开关、列表、照片、撤回、打包与手动上传。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from shedguard_server.api.dependencies import (
    get_contribution_export_repository,
    get_contribution_sample_repository,
    get_contribution_setting_repository,
    get_contribution_uploader,
    get_current_user,
    get_image_repository,
    get_metric_repository,
    get_pet_repository,
    get_push_device_repository,
    get_settings,
    get_storage,
    get_user_repository,
)
from shedguard_server.config import Settings
from shedguard_server.domain.contribution import (
    ContributionExport,
    ContributionSample,
    ContributionSetting,
    ContributionStats,
)
from shedguard_server.domain.user import User
from shedguard_server.errors import UnauthorizedError
from shedguard_server.infra.auth import hash_token
from shedguard_server.infra.contribution_upload import ContributionUploader
from shedguard_server.infra.repository import (
    ContributionExportRepository,
    ContributionSampleRepository,
    ContributionSettingRepository,
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    PushDeviceRepository,
    UserRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.contributions import ContributionService

router = APIRouter(prefix="/api/v1", tags=["contributions"])


class ContributionSettingsUpdate(BaseModel):
    """分享开关；两个字段都给，避免「只改一个」的歧义。"""

    enabled: bool
    include_full: bool


def get_contribution_service(
    settings_repo: Annotated[
        ContributionSettingRepository, Depends(get_contribution_setting_repository)
    ],
    samples: Annotated[
        ContributionSampleRepository, Depends(get_contribution_sample_repository)
    ],
    exports: Annotated[
        ContributionExportRepository, Depends(get_contribution_export_repository)
    ],
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    devices: Annotated[PushDeviceRepository, Depends(get_push_device_repository)],
    images: Annotated[ImageRepository, Depends(get_image_repository)],
    metrics: Annotated[FrameMetricRepository, Depends(get_metric_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    uploader: Annotated[ContributionUploader, Depends(get_contribution_uploader)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ContributionService:
    return ContributionService(
        settings=settings_repo,
        samples=samples,
        exports=exports,
        pets=pets,
        devices=devices,
        images=images,
        metrics=metrics,
        storage=storage,
        uploader=uploader,
        per_event_limit=settings.contribution_per_event_limit,
        max_pending=settings.contribution_max_pending,
        crop_padding=settings.contribution_crop_padding,
        upload_batch_size=settings.contribution_upload_batch,
    )


def serialize_setting(setting: ContributionSetting) -> dict[str, Any]:
    return {
        "enabled": setting.enabled,
        "include_full": setting.include_full,
        "updated_at_utc": setting.updated_at_utc.isoformat(),
    }


def serialize_sample(sample: ContributionSample) -> dict[str, Any]:
    return {
        "id": sample.id,
        "local_date": sample.local_date.isoformat(),
        "state": sample.state,
        "confidence": (
            round(sample.confidence, 4) if sample.confidence is not None else None
        ),
        "has_full": sample.has_full,
        "upload_status": sample.upload_status,
        "upload_attempts": sample.upload_attempts,
        "uploaded_at_utc": (
            sample.uploaded_at_utc.isoformat() if sample.uploaded_at_utc is not None else None
        ),
        "created_at_utc": sample.created_at_utc.isoformat(),
    }


def serialize_stats(stats: ContributionStats) -> dict[str, Any]:
    return {
        "total": stats.total,
        "pending": stats.pending,
        "uploaded": stats.uploaded,
        "failed": stats.failed,
        "withdrawn": stats.withdrawn,
    }


def serialize_export(export: ContributionExport) -> dict[str, Any]:
    return {
        "id": export.id,
        "filename": export.filename,
        "sample_count": export.sample_count,
        "byte_size": export.byte_size,
        "created_at_utc": export.created_at_utc.isoformat(),
    }


def _owner_from_token(
    request: Request,
    users: UserRepository,
    settings: Settings,
) -> str:
    """给 `<Image>`/下载链接用：允许 `?token=`，鉴权关闭时按本机账号处理。"""
    if not settings.auth_enabled:
        return "dev"
    raw = request.query_params.get("token", "")
    if not raw:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        raw = credential.strip() if scheme.lower() == "bearer" else ""
    resolved = users.find_by_token_hash(hash_token(raw)) if raw else None
    if resolved is None:
        raise UnauthorizedError("需要访问令牌")
    return resolved.id


@router.get("/contribution-settings")
def get_contribution_settings(
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return serialize_setting(service.get_settings(user.id))


@router.put("/contribution-settings")
def update_contribution_settings(
    payload: ContributionSettingsUpdate,
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    updated = service.update_settings(
        user.id, enabled=payload.enabled, include_full=payload.include_full
    )
    return serialize_setting(updated)


@router.get("/contributions")
def list_contributions(
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    items = service.list_for_owner(user.id, limit=limit)
    return {
        "items": [serialize_sample(sample) for sample in items],
        "stats": serialize_stats(service.stats(user.id)),
    }


@router.get("/contributions/{sample_id}/image")
def get_contribution_image(
    sample_id: str,
    request: Request,
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    full: Annotated[bool, Query(description="取整张原图（如果当初分享过）")] = False,
) -> Response:
    owner_id = _owner_from_token(request, users, settings)
    payload, media_type = service.read_sample(sample_id, owner_id=owner_id, full=full)
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.post("/contributions/{sample_id}/withdraw")
def withdraw_contribution(
    sample_id: str,
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return serialize_sample(service.withdraw(sample_id, owner_id=user.id))


@router.post("/contributions/export")
def create_contribution_export(
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    export = service.create_export(user.id)
    return JSONResponse(serialize_export(export), status_code=201)


@router.get("/contributions/exports/{export_id}")
def download_contribution_export(
    export_id: str,
    request: Request,
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    owner_id = _owner_from_token(request, users, settings)
    payload, media_type = service.read_export(export_id, owner_id=owner_id)
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{export_id}.zip"'},
    )


@router.post("/contributions/upload-now")
def upload_contributions_now(
    service: Annotated[ContributionService, Depends(get_contribution_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    summary = service.upload_pending()
    return {
        "uploaded": summary.uploaded,
        "failed": summary.failed,
        "skipped": summary.skipped,
    }

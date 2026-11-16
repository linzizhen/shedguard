"""摄像头接口：注册、列表、改配置、删除、测试连接、手动抓拍。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from shedguard_server.api.dependencies import (
    get_camera_repository,
    get_current_user,
    get_detector,
    get_pet_repository,
    get_settings,
    get_state_classifier,
    get_storage,
)
from shedguard_server.api.routes.images import get_ingest_service
from shedguard_server.config import Settings
from shedguard_server.domain.camera import Camera, redact_config
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.push import PushGateway
from shedguard_server.domain.shedding import StateClassifier
from shedguard_server.domain.user import User
from shedguard_server.infra.contribution_upload import ContributionUploader
from shedguard_server.infra.crypto import SecretBoxLike, build_secret_box
from shedguard_server.infra.repository import CameraRepository, PetRepository
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.cameras import CameraService
from shedguard_server.services.ingest import IngestService
from shedguard_server.services.processing import process_image

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])

Provider = Literal["ezviz", "rtsp"]


class CameraCreate(BaseModel):
    provider: Provider
    label: str = Field(min_length=1, max_length=64)
    pet_id: str | None = None
    config: dict[str, str] = Field(default_factory=dict)


class CameraUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    pet_id: str | None = None
    enabled: bool | None = None
    config: dict[str, str] | None = None


def _box(settings: Settings) -> SecretBoxLike:
    return build_secret_box(settings.secret_key)


def get_camera_service(
    cameras: Annotated[CameraRepository, Depends(get_camera_repository)],
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    ingest: Annotated[IngestService, Depends(get_ingest_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CameraService:
    return CameraService(
        cameras,
        pets,
        ingest,
        _box(settings),
        timezone=settings.tzinfo,
        timeout_seconds=settings.camera_timeout_seconds,
        max_failures=settings.camera_max_failures,
    )


def serialize_camera(camera: Camera) -> dict[str, Any]:
    """敏感字段一律不出现在响应里，只告诉前端「有没有存过密码」。"""
    return {
        "id": camera.id,
        "provider": camera.provider,
        "label": camera.label,
        "pet_id": camera.pet_id,
        "enabled": camera.enabled,
        "status": camera.status,
        "last_error": camera.last_error,
        "last_frame_at_utc": camera.last_frame_at_utc,
        "consecutive_failures": camera.consecutive_failures,
        "config": redact_config(camera.provider, camera.config),
        "has_secret": bool(camera.secret_enc),
        "created_at_utc": camera.created_at_utc,
        "updated_at_utc": camera.updated_at_utc,
    }


@router.post("", status_code=201)
def create_camera(
    body: CameraCreate,
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    camera = service.create(
        owner_id=user.id,
        provider=body.provider,
        label=body.label,
        pet_id=body.pet_id,
        config=body.config,
    )
    return JSONResponse(serialize_camera(camera), status_code=201)


@router.get("")
def list_cameras(
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    items = service.list(user.id)
    return {"items": [serialize_camera(camera) for camera in items]}


@router.patch("/{camera_id}")
def update_camera(
    camera_id: str,
    body: CameraUpdate,
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    camera = service.update(
        camera_id,
        owner_id=user.id,
        label=body.label,
        pet_id=body.pet_id,
        update_pet="pet_id" in body.model_fields_set,
        enabled=body.enabled,
        config=body.config,
    )
    return serialize_camera(camera)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(
    camera_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    service.delete(camera_id, owner_id=user.id)
    return Response(status_code=204)


@router.post("/{camera_id}/test")
async def test_camera(
    camera_id: str,
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    result = await run_in_threadpool(service.test, camera_id, owner_id=user.id)
    return {
        "ok": result.ok,
        "kind": result.kind,
        "detail": result.detail,
        "took_ms": result.took_ms,
    }


@router.post("/{camera_id}/snapshot", status_code=202)
async def snapshot_camera(
    camera_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service: Annotated[CameraService, Depends(get_camera_service)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    detector: Annotated[Detector, Depends(get_detector)],
    classifier: Annotated[StateClassifier | None, Depends(get_state_classifier)],
) -> JSONResponse:
    result = await run_in_threadpool(service.snapshot, camera_id, owner_id=user.id)
    gateway: PushGateway = request.app.state.push_gateway
    uploader: ContributionUploader = request.app.state.contribution_uploader
    background_tasks.add_task(
        process_image,
        session_factory=request.app.state.session_factory,
        settings=settings,
        detector=detector,
        classifier=classifier,
        storage=storage,
        gateway=gateway,
        contribution_uploader=uploader,
        image_id=result.image.record.id,
    )
    body = {
        "image_id": result.image.record.id,
        "device_id": result.image.record.device_id,
        "duplicate": result.image.duplicate,
        "captured_at_utc": result.image.record.captured_at_utc.isoformat().replace("+00:00", "Z"),
    }
    return JSONResponse(body, status_code=202)
"""图片接入接口：上传、按天列表、取原图、取元数据。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from shedguard_server.api.dependencies import (
    get_detector,
    get_settings,
    get_state_classifier,
    get_storage,
)
from shedguard_server.api.dependencies import (
    get_image_repository as get_repository,
)
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.models import ImageRecord
from shedguard_server.domain.push import PushGateway
from shedguard_server.domain.shedding import StateClassifier
from shedguard_server.errors import InvalidRequestError, NotFoundError, PayloadTooLargeError
from shedguard_server.infra.repository import ImageRepository
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.ingest import IngestService
from shedguard_server.services.processing import process_image

router = APIRouter(prefix="/api/v1/images", tags=["images"])

# multipart 的边界与头部开销，用于按 Content-Length 提前拒绝超大请求。
_MULTIPART_OVERHEAD = 8192

_MEDIA_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


def get_ingest_service(
    repository: Annotated[ImageRepository, Depends(get_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestService:
    return IngestService(
        repository,
        storage,
        timezone=settings.tzinfo,
        max_upload_bytes=settings.max_upload_bytes,
    )


def _serialize(record: ImageRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "device_id": record.device_id,
        "rel_path": record.rel_path,
        "byte_size": record.byte_size,
        "sha256": record.sha256,
        "captured_at_utc": record.captured_at_utc.isoformat().replace("+00:00", "Z"),
        "local_date": record.local_date.isoformat(),
        "received_at_utc": record.received_at_utc.isoformat().replace("+00:00", "Z"),
    }


async def _read_payload(request: Request, limit: int) -> bytes:
    """同时支持 multipart 字段 file 与裸 image/* 请求体。"""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit + _MULTIPART_OVERHEAD:
        raise PayloadTooLargeError(f"请求体超过上限 {limit} 字节")

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            for value in form.values():
                if isinstance(value, UploadFile):
                    upload = value
                    break
        if not isinstance(upload, UploadFile):
            raise InvalidRequestError("multipart 请求必须包含字段 file")
        return await upload.read()
    return await request.body()


@router.post("", status_code=201)
async def upload_image(
    request: Request,
    background_tasks: BackgroundTasks,
    service: Annotated[IngestService, Depends(get_ingest_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    detector: Annotated[Detector, Depends(get_detector)],
    classifier: Annotated[StateClassifier | None, Depends(get_state_classifier)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
) -> JSONResponse:
    payload = await _read_payload(request, settings.max_upload_bytes)
    outcome = await run_in_threadpool(
        service.ingest,
        payload,
        device_id_raw=request.headers.get("x-device-id"),
        captured_at_raw=request.headers.get("x-captured-at"),
    )
    if not outcome.duplicate and settings.auto_process:
        gateway: PushGateway = request.app.state.push_gateway
        background_tasks.add_task(
            process_image,
            session_factory=request.app.state.session_factory,
            settings=settings,
            detector=detector,
            classifier=classifier,
            storage=storage,
            gateway=gateway,
            image_id=outcome.record.id,
        )
    body = {**_serialize(outcome.record), "duplicate": outcome.duplicate}
    return JSONResponse(body, status_code=200 if outcome.duplicate else 201)


@router.get("")
def list_images(
    repository: Annotated[ImageRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    day: Annotated[str | None, Query(alias="date")] = None,
    device_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    if day is None:
        target = date.today()
    else:
        try:
            target = date.fromisoformat(day)
        except ValueError as exc:
            raise InvalidRequestError(f"date 必须是 YYYY-MM-DD: {day!r}") from exc
    items, total = repository.list_for_date(
        target.isoformat(),
        device_id=device_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_serialize(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{image_id}/metadata")
def get_image_metadata(
    image_id: str,
    repository: Annotated[ImageRepository, Depends(get_repository)],
) -> dict[str, Any]:
    record = repository.find_by_id(image_id)
    if record is None:
        raise NotFoundError(f"图片不存在: {image_id}")
    return _serialize(record)


@router.get("/{image_id}")
def get_image(
    image_id: str,
    repository: Annotated[ImageRepository, Depends(get_repository)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
) -> Response:
    record = repository.find_by_id(image_id)
    if record is None:
        raise NotFoundError(f"图片不存在: {image_id}")
    payload = storage.read(record.rel_path)
    extension = record.rel_path.rsplit(".", 1)[-1].lower()
    return Response(
        content=payload,
        media_type=_MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={"ETag": f'"{record.sha256}"', "Cache-Control": "immutable"},
    )
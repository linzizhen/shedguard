"""宠物档案、蜕皮日志、周期预测与拍照查验接口。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shedguard_server.api.dependencies import (
    get_current_user,
    get_pet_repository,
    get_settings,
    get_shed_record_repository,
)
from shedguard_server.api.params import parse_day
from shedguard_server.config import Settings
from shedguard_server.domain.pets import Pet, ShedRecord
from shedguard_server.domain.user import User
from shedguard_server.errors import InvalidRequestError, PayloadTooLargeError
from shedguard_server.infra.repository import PetRepository, ShedRecordRepository
from shedguard_server.services.ingest import IngestService
from shedguard_server.services.pets import CheckPhotoService, PetService, ShedRecordService
from shedguard_server.services.shedding import SheddingService

from .images import get_ingest_service
from .shedding import get_shedding_service

router = APIRouter(prefix="/api/v1/pets", tags=["pets"])

_MULTIPART_OVERHEAD = 8192


class PetCreate(BaseModel):
    """创建宠物的请求体。"""

    name: str = Field(min_length=1, max_length=64)
    species: str = Field(default="豹纹守宫", max_length=64)
    morph: str | None = Field(default=None, max_length=64)
    birth_date: date | None = None


class PetUpdate(BaseModel):
    """更新宠物的请求体；全部字段可选。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    species: str | None = Field(default=None, max_length=64)
    morph: str | None = Field(default=None, max_length=64)
    birth_date: date | None = None


class ShedRecordCreate(BaseModel):
    """创建蜕皮记录的请求体。"""

    started_on: date
    completed_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ShedRecordUpdate(BaseModel):
    """更新蜕皮记录的请求体；全部字段可选。"""

    started_on: date | None = None
    completed_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


def get_pet_service(
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    records: Annotated[ShedRecordRepository, Depends(get_shed_record_repository)],
) -> PetService:
    return PetService(pets, records)


def get_shed_record_service(
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    records: Annotated[ShedRecordRepository, Depends(get_shed_record_repository)],
) -> ShedRecordService:
    return ShedRecordService(pets, records)


def get_check_photo_service(
    pets: Annotated[PetRepository, Depends(get_pet_repository)],
    ingest: Annotated[IngestService, Depends(get_ingest_service)],
    shedding: Annotated[SheddingService, Depends(get_shedding_service)],
) -> CheckPhotoService:
    return CheckPhotoService(pets, ingest, shedding)


def serialize_pet(pet: Pet) -> dict[str, Any]:
    return {
        "id": pet.id,
        "name": pet.name,
        "species": pet.species,
        "morph": pet.morph,
        "birth_date": pet.birth_date.isoformat() if pet.birth_date else None,
        "created_at_utc": pet.created_at_utc.isoformat(),
        "updated_at_utc": pet.updated_at_utc.isoformat(),
    }


def serialize_record(record: ShedRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "pet_id": record.pet_id,
        "started_on": record.started_on.isoformat(),
        "completed_on": record.completed_on.isoformat() if record.completed_on else None,
        "notes": record.notes,
        "created_at_utc": record.created_at_utc.isoformat(),
        "updated_at_utc": record.updated_at_utc.isoformat(),
    }


@router.get("")
def list_pets(
    service: Annotated[PetService, Depends(get_pet_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return {"items": [serialize_pet(pet) for pet in service.list(owner_id=user.id)]}


@router.post("", status_code=201)
def create_pet(
    body: PetCreate,
    service: Annotated[PetService, Depends(get_pet_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    pet = service.create(
        name=body.name,
        species=body.species,
        morph=body.morph,
        birth_date=body.birth_date,
        owner_id=user.id,
    )
    return JSONResponse(serialize_pet(pet), status_code=201)


@router.get("/{pet_id}")
def get_pet(
    pet_id: str,
    service: Annotated[PetService, Depends(get_pet_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return serialize_pet(service.get(pet_id, owner_id=user.id))


@router.put("/{pet_id}")
def update_pet(
    pet_id: str,
    body: PetUpdate,
    service: Annotated[PetService, Depends(get_pet_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    pet = service.update(
        pet_id,
        name=body.name,
        species=body.species,
        morph=body.morph,
        birth_date=body.birth_date,
        owner_id=user.id,
    )
    return serialize_pet(pet)


@router.delete("/{pet_id}", status_code=204)
def delete_pet(
    pet_id: str,
    service: Annotated[PetService, Depends(get_pet_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    service.delete(pet_id, owner_id=user.id)


@router.get("/{pet_id}/shed-records")
def list_shed_records(
    pet_id: str,
    service: Annotated[ShedRecordService, Depends(get_shed_record_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return {
        "items": [
            serialize_record(r) for r in service.list_for_pet(pet_id, owner_id=user.id)
        ]
    }


@router.post("/{pet_id}/shed-records", status_code=201)
def create_shed_record(
    pet_id: str,
    body: ShedRecordCreate,
    service: Annotated[ShedRecordService, Depends(get_shed_record_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    record = service.create(
        pet_id,
        started_on=body.started_on,
        completed_on=body.completed_on,
        notes=body.notes,
        owner_id=user.id,
    )
    return JSONResponse(serialize_record(record), status_code=201)


@router.put("/{pet_id}/shed-records/{record_id}")
def update_shed_record(
    pet_id: str,
    record_id: str,
    body: ShedRecordUpdate,
    service: Annotated[ShedRecordService, Depends(get_shed_record_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    record = service.update(
        pet_id,
        record_id,
        started_on=body.started_on,
        completed_on=body.completed_on,
        notes=body.notes,
        owner_id=user.id,
    )
    return serialize_record(record)


@router.delete("/{pet_id}/shed-records/{record_id}", status_code=204)
def delete_shed_record(
    pet_id: str,
    record_id: str,
    service: Annotated[ShedRecordService, Depends(get_shed_record_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    service.delete(pet_id, record_id, owner_id=user.id)


@router.get("/{pet_id}/shed-prediction")
def get_shed_prediction(
    pet_id: str,
    service: Annotated[ShedRecordService, Depends(get_shed_record_service)],
    user: Annotated[User, Depends(get_current_user)],
    today: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    target = parse_day(today, "today") if today else datetime.now().date()
    prediction = service.predict(pet_id, today=target, owner_id=user.id)
    return {
        "predictable": prediction.predictable,
        "reason": prediction.reason,
        "median_interval_days": prediction.median_interval_days,
        "mad_days": prediction.mad_days,
        "next_window_start": (
            prediction.next_window_start.isoformat() if prediction.next_window_start else None
        ),
        "next_window_end": (
            prediction.next_window_end.isoformat() if prediction.next_window_end else None
        ),
        "based_on_cycles": prediction.based_on_cycles,
    }


@router.post("/{pet_id}/check-photo")
async def check_photo(
    pet_id: str,
    request: Request,
    service: Annotated[CheckPhotoService, Depends(get_check_photo_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    """上传一张守宫照片，返回蜕皮状态判断与照护建议。"""
    declared = request.headers.get("content-length")
    if (
        declared is not None
        and declared.isdigit()
        and int(declared) > settings.max_upload_bytes + _MULTIPART_OVERHEAD
    ):
        raise PayloadTooLargeError(f"请求体超过上限 {settings.max_upload_bytes} 字节")
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        from starlette.datastructures import UploadFile

        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            for value in form.values():
                if isinstance(value, UploadFile):
                    upload = value
                    break
        if not isinstance(upload, UploadFile):
            raise InvalidRequestError("multipart 请求必须包含字段 file")
        payload = await upload.read()
    else:
        payload = await request.body()
    if not payload:
        raise InvalidRequestError("图片内容为空")
    result = await run_in_threadpool(service.check, pet_id, payload, owner_id=user.id)
    probabilities = (
        {k: round(v, 4) for k, v in result.probabilities.items()}
        if result.probabilities
        else None
    )
    return JSONResponse(
        {
            "image_id": result.image_id,
            "state": result.state,
            "confidence": round(result.confidence, 4) if result.confidence is not None else None,
            "probabilities": probabilities,
            "advice": result.advice,
        }
    )

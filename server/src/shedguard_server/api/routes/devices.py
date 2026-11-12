"""推送设备注册接口。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shedguard_server.api.dependencies import (
    get_current_user,
    get_push_device_repository,
)
from shedguard_server.domain.alerts import PushDevice
from shedguard_server.domain.user import User
from shedguard_server.errors import NotFoundError
from shedguard_server.infra.repository import PushDeviceRepository

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class DeviceRegister(BaseModel):
    """App 上报推送 token 的请求体。"""

    expo_push_token: str = Field(default="", max_length=255)
    platform: Literal["ios", "android", "web"]
    device_id: str | None = Field(default=None, max_length=64)
    pet_id: str | None = Field(default=None, max_length=36)


def serialize_device(device: PushDevice) -> dict[str, Any]:
    return {
        "id": device.id,
        "device_id": device.device_id,
        "pet_id": device.pet_id,
        "expo_push_token": device.expo_push_token,
        "platform": device.platform,
        "created_at_utc": device.created_at_utc.isoformat(),
        "updated_at_utc": device.updated_at_utc.isoformat(),
    }


@router.post("", status_code=201)
def register_device(
    body: DeviceRegister,
    repository: Annotated[PushDeviceRepository, Depends(get_push_device_repository)],
    user: Annotated[User, Depends(get_current_user)],
) -> JSONResponse:
    now = datetime.now(UTC)
    device = PushDevice(
        id=str(uuid4()),
        device_id=body.device_id,
        pet_id=body.pet_id,
        expo_push_token=body.expo_push_token,
        platform=body.platform,
        created_at_utc=now,
        updated_at_utc=now,
        owner_id=user.id,
    )
    saved = repository.upsert(device)
    return JSONResponse(serialize_device(saved), status_code=201)


@router.delete("/{device_pk}", status_code=204)
def delete_device(
    device_pk: str,
    repository: Annotated[PushDeviceRepository, Depends(get_push_device_repository)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    device = repository.get(device_pk)
    if device is None or (device.owner_id is not None and device.owner_id != user.id):
        raise NotFoundError(f"设备不存在: {device_pk}")
    repository.delete(device_pk)

"""匿名账号接口：换取令牌、查询当前身份。

没有注册/登录表单：App 首次启动调 `/anonymous` 拿 token，
之后所有需要身份的接口都用 `Authorization: Bearer <token>`。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from shedguard_server.api.dependencies import get_current_user, get_user_repository
from shedguard_server.domain.user import User
from shedguard_server.ids import new_request_id
from shedguard_server.infra.auth import hash_token, new_token
from shedguard_server.infra.repository import UserRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "created_at_utc": user.created_at_utc.isoformat(),
        "last_seen_at_utc": (
            user.last_seen_at_utc.isoformat() if user.last_seen_at_utc else None
        ),
    }


@router.post("/anonymous", status_code=201)
def register_anonymous(
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> JSONResponse:
    """新建一个匿名账号；明文令牌只在这里返回一次。"""
    token = new_token()
    user = User(id=new_request_id(), created_at_utc=datetime.now(UTC))
    users.add(user, hash_token(token))
    return JSONResponse({"user_id": user.id, "token": token}, status_code=201)


@router.get("/me")
def get_me(user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    return serialize_user(user)

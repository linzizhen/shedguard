"""统一错误契约：所有对外错误都走同一套错误码与响应体结构。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """对外错误码，取值即响应体中的字符串。"""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    EMPTY_PAYLOAD = "EMPTY_PAYLOAD"
    NOT_FOUND = "NOT_FOUND"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """业务错误基类；子类只覆盖 code 与 status_code。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequestError(ApiError):
    code = ErrorCode.INVALID_REQUEST
    status_code = 400


class UnsupportedMediaTypeError(ApiError):
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    status_code = 415


class PayloadTooLargeError(ApiError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    status_code = 413


class EmptyPayloadError(ApiError):
    code = ErrorCode.EMPTY_PAYLOAD
    status_code = 400


class NotFoundError(ApiError):
    code = ErrorCode.NOT_FOUND
    status_code = 404


class StorageUnavailableError(ApiError):
    code = ErrorCode.STORAGE_UNAVAILABLE
    status_code = 503


class InternalError(ApiError):
    code = ErrorCode.INTERNAL_ERROR
    status_code = 500


def error_payload(error: ApiError, request_id: str | None) -> dict[str, Any]:
    """构造统一错误响应体。"""
    return {
        "error": {
            "code": error.code.value,
            "message": error.message,
            "request_id": request_id,
        }
    }
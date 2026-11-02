"""统一错误契约：错误码、HTTP 状态与响应体结构。"""

import pytest

from shedguard_server.errors import (
    ApiError,
    EmptyPayloadError,
    ErrorCode,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    StorageUnavailableError,
    UnsupportedMediaTypeError,
    error_payload,
)


@pytest.mark.parametrize(
    ("error_cls", "expected_code", "expected_status"),
    [
        (InvalidRequestError, ErrorCode.INVALID_REQUEST, 400),
        (UnsupportedMediaTypeError, ErrorCode.UNSUPPORTED_MEDIA_TYPE, 415),
        (PayloadTooLargeError, ErrorCode.PAYLOAD_TOO_LARGE, 413),
        (EmptyPayloadError, ErrorCode.EMPTY_PAYLOAD, 400),
        (NotFoundError, ErrorCode.NOT_FOUND, 404),
        (StorageUnavailableError, ErrorCode.STORAGE_UNAVAILABLE, 503),
        (InternalError, ErrorCode.INTERNAL_ERROR, 500),
    ],
)
def test_error_class_carries_code_and_status(
    error_cls: type[ApiError],
    expected_code: ErrorCode,
    expected_status: int,
) -> None:
    error = error_cls("出问题了")

    assert error.code is expected_code
    assert error.status_code == expected_status
    assert error.message == "出问题了"
    assert str(error) == "出问题了"


def test_code_serializes_to_its_name() -> None:
    assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
    assert str(ErrorCode.NOT_FOUND) == "NOT_FOUND"


def test_payload_has_error_envelope() -> None:
    payload = error_payload(NotFoundError("图片不存在"), request_id="req-123")

    assert payload == {
        "error": {
            "code": "NOT_FOUND",
            "message": "图片不存在",
            "request_id": "req-123",
        }
    }


def test_payload_tolerates_missing_request_id() -> None:
    payload = error_payload(InternalError("内部错误"), request_id=None)

    assert payload["error"]["request_id"] is None
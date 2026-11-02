"""输入校验：魔数、device_id 与大小。"""

import pytest

from shedguard_server.domain.validation import (
    DEFAULT_DEVICE_ID,
    sniff_image_extension,
    validate_device_id,
    validate_payload_size,
)
from shedguard_server.errors import (
    EmptyPayloadError,
    InvalidRequestError,
    PayloadTooLargeError,
)

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF"
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG_HEADER, "jpg"),
        (PNG_HEADER, "png"),
        (b"GIF89a\x01\x00", None),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", None),
        (b"\xff\xd8", None),
        (b"\x89PNG\r\n", None),
        (b"", None),
    ],
)
def test_sniff_image_extension(data: bytes, expected: str | None) -> None:
    assert sniff_image_extension(data) == expected


@pytest.mark.parametrize(
    "device_id",
    ["eye-01", "UNKNOWN", "a", "A1_b-2", "x" * 64],
)
def test_valid_device_ids_pass_through(device_id: str) -> None:
    assert validate_device_id(device_id) == device_id


@pytest.mark.parametrize(
    "device_id",
    ["", " ", "eye 01", "../etc/passwd", "eye/01", "eye\\01", "x" * 65, "眼睛"],
)
def test_invalid_device_ids_are_rejected(device_id: str) -> None:
    with pytest.raises(InvalidRequestError):
        validate_device_id(device_id)


def test_missing_device_id_defaults() -> None:
    assert validate_device_id(None) == DEFAULT_DEVICE_ID
    assert DEFAULT_DEVICE_ID == "unknown"


def test_empty_payload_rejected() -> None:
    with pytest.raises(EmptyPayloadError):
        validate_payload_size(0, limit=1024)


def test_oversized_payload_rejected() -> None:
    with pytest.raises(PayloadTooLargeError):
        validate_payload_size(1025, limit=1024)


def test_size_at_limit_passes() -> None:
    validate_payload_size(1024, limit=1024)
"""摄像头领域纯逻辑与凭据加密的单元测试。"""

from __future__ import annotations

import pytest

from shedguard_server.domain.camera import (
    ALERT_KIND_CAMERA_OFFLINE,
    CAMERA_PROVIDER_EZVIZ,
    CAMERA_PROVIDER_RTSP,
    DEVICE_ID_PREFIX,
    ERROR_AUTH_FAILED,
    ERROR_NO_FRAME,
    ERROR_UNREACHABLE,
    Camera,
    CameraError,
    camera_device_id,
    camera_id_from_device_id,
    redact_config,
    redact_rtsp_url,
    split_secret_config,
    status_for_failure,
)
from shedguard_server.infra.crypto import (
    EMPTY_SECRET_MESSAGE,
    NullSecretBox,
    SecretBoxError,
    build_secret_box,
    generate_key,
)


def _camera(**overrides: object) -> Camera:
    payload: dict[str, object] = {
        "id": "cam-1",
        "owner_id": "user-1",
        "pet_id": None,
        "provider": CAMERA_PROVIDER_RTSP,
        "label": "客厅",
        "config": {"url": "rtsp://192.168.1.9/stream"},
        "secret_enc": "",
    }
    payload.update(overrides)
    return Camera(**payload)  # type: ignore[arg-type]


class TestDeviceId:
    def test_prefix_round_trip(self) -> None:
        camera = _camera()
        assert camera.device_id == f"{DEVICE_ID_PREFIX}{camera.id}"
        assert camera_id_from_device_id(camera.device_id) == camera.id
        assert camera_device_id("abc") == f"{DEVICE_ID_PREFIX}abc"

    def test_foreign_device_id_is_rejected(self) -> None:
        assert camera_id_from_device_id("gecko-eye-01") is None
        assert camera_id_from_device_id(DEVICE_ID_PREFIX) is None


class TestSecrets:
    def test_rtsp_split(self) -> None:
        public, private = split_secret_config(
            CAMERA_PROVIDER_RTSP,
            {"url": "rtsp://cam/1", "user": "admin", "credential": "hunter2"},
        )
        assert public == {"url": "rtsp://cam/1"}
        assert private == {"user": "admin", "credential": "hunter2"}

    def test_unknown_config_key_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            split_secret_config(CAMERA_PROVIDER_RTSP, {"url": "rtsp://cam/1", "weird": "x"})

    def test_ezviz_split(self) -> None:
        public, private = split_secret_config(
            CAMERA_PROVIDER_EZVIZ,
            {"device_serial": "AA123", "channel": "1", "app_key": "k", "app_secret": "s"},
        )
        assert public == {"device_serial": "AA123", "channel": "1", "app_key": "k"}
        assert private == {"app_secret": "s"}

    def test_redact_rtsp_url_drops_credentials(self) -> None:
        assert redact_rtsp_url("rtsp://u:p@192.168.1.9/stream") == "rtsp://u:***@192.168.1.9/stream"

    def test_redact_config_keeps_public_only(self) -> None:
        payload = redact_config(
            CAMERA_PROVIDER_RTSP,
            {"url": "rtsp://u:p@192.168.1.9/s", "user": "u", "credential": "p"},
        )
        assert payload == {"url": "rtsp://u:***@192.168.1.9/s"}


class TestStatus:
    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            (ERROR_AUTH_FAILED, "auth_failed"),
            (ERROR_UNREACHABLE, "unreachable"),
            (ERROR_NO_FRAME, "unreachable"),
        ],
    )
    def test_status_for_failure(self, kind: str, expected: str) -> None:
        assert status_for_failure(kind) == expected

    def test_unknown_error_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            CameraError("weird", "…")
        assert status_for_failure("weird") == "unreachable"

    def test_alert_kind_is_stable(self) -> None:
        assert ALERT_KIND_CAMERA_OFFLINE == "camera_offline"


class TestSecretBox:
    def test_round_trip(self) -> None:
        box = build_secret_box(generate_key())
        token = box.encrypt({"user": "admin", "credential": "hunter2"})
        assert box.configured
        assert token != ""
        assert box.decrypt(token) == {"user": "admin", "credential": "hunter2"}

    def test_empty_key_disables_storage(self) -> None:
        box = build_secret_box("")
        assert isinstance(box, NullSecretBox)
        assert not box.configured
        with pytest.raises(SecretBoxError) as caught:
            box.encrypt({"credential": "x"})
        assert str(caught.value) == EMPTY_SECRET_MESSAGE

    def test_broken_key_is_rejected(self) -> None:
        with pytest.raises(SecretBoxError):
            build_secret_box("not-a-key")

    def test_wrong_key_cannot_decrypt(self) -> None:
        token = build_secret_box(generate_key()).encrypt({"credential": "x"})
        other = build_secret_box(generate_key())
        with pytest.raises(SecretBoxError):
            other.decrypt(token)

    def test_generate_key_is_valid(self) -> None:
        assert build_secret_box(generate_key()).configured
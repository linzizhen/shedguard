"""摄像头适配器的单元测试：只验协议与错误映射，不碰真网络。"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from shedguard_server.domain.camera import (
    CAMERA_PROVIDER_EZVIZ,
    CAMERA_PROVIDER_RTSP,
    ERROR_AUTH_FAILED,
    ERROR_BAD_CONFIG,
    ERROR_NO_FRAME,
    ERROR_UNREACHABLE,
    Camera,
    CameraError,
)
from shedguard_server.infra.camera_sources import (
    EzvizSource,
    RtspSource,
    build_camera_source,
)


def _camera(provider: str, config: dict[str, str]) -> Camera:
    return Camera(
        id="cam-1",
        owner_id="user-1",
        pet_id=None,
        provider=provider,
        label="客厅",
        config=config,
    )


class _FakeApi:
    def __init__(self, token: str = "tok", url: str = "rtsp://cloud/1") -> None:
        self.token = token
        self.url = url
        self.calls: list[tuple[str, dict[str, object]]] = []

    def access_token(self, *, app_key: str, app_secret: str) -> str:
        self.calls.append(("token", {"app_key": app_key, "app_secret": app_secret}))
        return self.token

    def live_address(self, *, token: str, device_serial: str, channel: int) -> str:
        self.calls.append(
            ("live", {"token": token, "device_serial": device_serial, "channel": channel})
        )
        return self.url


class TestBuildSource:
    def test_rtsp_keeps_url(self) -> None:
        camera = _camera(CAMERA_PROVIDER_RTSP, {"url": "rtsp://192.168.1.9/s"})
        source = build_camera_source(camera, {})
        assert isinstance(source, RtspSource)
        assert source.url == "rtsp://192.168.1.9/s"

    def test_rtsp_injects_credentials(self) -> None:
        camera = _camera(CAMERA_PROVIDER_RTSP, {"url": "rtsp://192.168.1.9/s"})
        source = build_camera_source(camera, {"user": "admin", "credential": "p@ss"})
        assert isinstance(source, RtspSource)
        assert source.url == f"rtsp://admin:{quote('p@ss')}@192.168.1.9/s"
        assert source.name == "rtsp"

    def test_rtsp_without_url_is_bad_config(self) -> None:
        camera = _camera(CAMERA_PROVIDER_RTSP, {})
        with pytest.raises(CameraError) as caught:
            build_camera_source(camera, {})
        assert caught.value.kind == ERROR_BAD_CONFIG

    def test_ezviz_requires_secrets(self) -> None:
        camera = _camera(CAMERA_PROVIDER_EZVIZ, {"device_serial": "AA1", "app_key": "k"})
        with pytest.raises(CameraError) as caught:
            build_camera_source(camera, {})
        assert caught.value.kind == ERROR_BAD_CONFIG

    def test_ezviz_builds_source(self) -> None:
        camera = _camera(
            CAMERA_PROVIDER_EZVIZ, {"device_serial": "AA1", "app_key": "k", "channel": "2"}
        )
        source = build_camera_source(camera, {"app_secret": "s"}, ezviz_api=_FakeApi())
        assert isinstance(source, EzvizSource)
        assert source.channel == 2


class TestSources:
    def test_ezviz_fetches_token_then_frame(self) -> None:
        api = _FakeApi(url="rtsp://cloud/1")
        grabbed: list[str] = []

        def grabber(url: str, *, timeout_seconds: float = 15.0) -> bytes:
            grabbed.append(url)
            return b"jpeg"

        source = EzvizSource(
            api=api, app_key="k", app_secret="s", device_serial="AA1", grabber=grabber
        )
        assert source.fetch_frame() == b"jpeg"
        assert grabbed == ["rtsp://cloud/1"]
        assert [name for name, _ in api.calls] == ["token", "live"]

    def test_rtsp_passes_timeout_to_grabber(self) -> None:
        seen: list[float] = []

        def grabber(url: str, *, timeout_seconds: float = 15.0) -> bytes:
            seen.append(timeout_seconds)
            return b"jpeg"

        source = RtspSource(url="rtsp://x/1", timeout_seconds=3.0, grabber=grabber)
        assert source.fetch_frame() == b"jpeg"
        assert seen == [3.0]

    def test_grabber_errors_are_propagated(self) -> None:
        def grabber(url: str, *, timeout_seconds: float = 15.0) -> bytes:
            raise CameraError(ERROR_UNREACHABLE, "连不上")

        source = RtspSource(url="rtsp://x/1", grabber=grabber)
        with pytest.raises(CameraError) as caught:
            source.fetch_frame()
        assert caught.value.kind == ERROR_UNREACHABLE

    def test_ezviz_auth_failure_is_mapped(self) -> None:
        class _BrokenApi(_FakeApi):
            def access_token(self, *, app_key: str, app_secret: str) -> str:
                raise CameraError(ERROR_AUTH_FAILED, "应用密钥不对")

        source = EzvizSource(
            api=_BrokenApi(), app_key="k", app_secret="s", device_serial="AA1"
        )
        with pytest.raises(CameraError) as caught:
            source.fetch_frame()
        assert caught.value.kind == ERROR_AUTH_FAILED


class TestErrorKinds:
    def test_no_frame_kind_exists(self) -> None:
        assert ERROR_NO_FRAME == "no_frame"

class TestGrabTimeout:
    """连不通的地址会挂很久：必须被超时切断，而不是把后台循环拖死。"""

    def test_slow_capture_raises_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        from shedguard_server.infra import camera_sources

        def slow(url: str) -> bytes:
            time.sleep(0.4)
            return b"never"

        monkeypatch.setattr(camera_sources, "_capture_jpeg", slow)
        with pytest.raises(CameraError) as caught:
            camera_sources.grab_frame_from_url("rtsp://example/stream", timeout_seconds=0.05)
        assert caught.value.kind == ERROR_UNREACHABLE
        assert "超时" in caught.value.detail

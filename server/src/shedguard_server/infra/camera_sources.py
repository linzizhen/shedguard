"""把「一台摄像头」变成「一张 JPEG」的适配器。

两种实现：
- `RtspSource`：直接用 RTSP 地址抓一帧（需要服务端能路由到摄像头）。
- `EzvizSource`：先走萤石开放平台拿直播地址，再从该地址抓一帧。

⚠️ 萤石云的两个接口路径是按公开文档写的，**账号开通后需要按最新文档再核一次**
（`docs/specs/2026-11-16-camera-adapter-design.md` §5 也标注了这一点）。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import quote

import cv2
import httpx
import numpy as np

from shedguard_server.domain.camera import (
    CAMERA_PROVIDER_EZVIZ,
    CAMERA_PROVIDER_RTSP,
    ERROR_AUTH_FAILED,
    ERROR_BAD_CONFIG,
    ERROR_NO_FRAME,
    ERROR_UNREACHABLE,
    Camera,
    CameraError,
    CameraSource,
)

EZVIZ_BASE_URL: Final = "https://open.ys7.com"
EZVIZ_TOKEN_PATH: Final = "/api/lapp/token/get"
EZVIZ_LIVE_PATH: Final = "/api/lapp/live/address/get"
DEFAULT_CHANNEL: Final = 1
JPEG_QUALITY: Final = 90

# 抓帧线程池：小规模够用，卡住的线程会自己超时退出，不会无限堆积。
_GRABBER: Final = ThreadPoolExecutor(max_workers=4, thread_name_prefix="camera-grab")

class Grabber(Protocol):
    """取一帧的可注入点：测试里换成假实现，生产里是 OpenCV。"""

    def __call__(self, url: str, *, timeout_seconds: float = 15.0) -> bytes: ...


def grab_frame_from_url(url: str, *, timeout_seconds: float = 15.0) -> bytes:
    """用 OpenCV 从 RTSP / HTTP 流里取一帧，编码成 JPEG。

    OpenCV 的 `CAP_PROP_OPEN_TIMEOUT_MSEC` 只在部分后端生效，连不通的地址
    可能挂上几十秒。所以这里把真正的抓帧放到工作线程里，用 `result(timeout=...)`
    硬性切断等待——否则一次坏地址就能把后台抓拍循环拖死。
    """
    future = _GRABBER.submit(_capture_jpeg, url)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        raise CameraError(
            ERROR_UNREACHABLE, "连摄像头超时了，检查地址、电源和网络"
        ) from None


def _capture_jpeg(url: str) -> bytes:
    capture = cv2.VideoCapture(url)
    try:
        if not capture.isOpened():
            raise CameraError(ERROR_UNREACHABLE, "连不上摄像头，检查地址和网络")
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise CameraError(ERROR_NO_FRAME, "摄像头没给出画面，可能正在重启")
    ok, encoded = cv2.imencode(
        ".jpg", np.asarray(frame), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    )
    if not ok:
        raise CameraError(ERROR_NO_FRAME, "这一帧没能转成图片")
    return encoded.tobytes()


class EzvizApi(Protocol):
    def access_token(self, *, app_key: str, app_secret: str) -> str: ...

    def live_address(self, *, token: str, device_serial: str, channel: int) -> str: ...


@dataclass(frozen=True, slots=True)
class HttpxEzvizApi:
    """萤石开放平台的最小客户端；只实现拿 token 与取流地址两个调用。"""

    base_url: str = EZVIZ_BASE_URL
    timeout_seconds: float = 15.0
    transport: httpx.BaseTransport | None = None

    def _post(self, path: str, data: dict[str, str]) -> dict[str, object]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, trust_env=False, transport=self.transport
            ) as client:
                response = client.post(
                    f"{self.base_url}{path}", data=data, headers={"User-Agent": "shedguard/0.1"}
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CameraError(ERROR_UNREACHABLE, "萤石云连不上，稍后再试") from exc
        if not isinstance(payload, dict):
            raise CameraError(ERROR_AUTH_FAILED, "萤石云返回了看不懂的内容")
        code = str(payload.get("code", ""))
        if code != "200":
            message = str(payload.get("msg", "授权失败，请重新登录萤石账号"))
            raise CameraError(ERROR_AUTH_FAILED, message)
        body = payload.get("data")
        if not isinstance(body, dict):
            raise CameraError(ERROR_AUTH_FAILED, "萤石云没有返回数据")
        return body

    def access_token(self, *, app_key: str, app_secret: str) -> str:
        body = self._post(EZVIZ_TOKEN_PATH, {"appKey": app_key, "appSecret": app_secret})
        token = body.get("accessToken")
        if not isinstance(token, str) or not token:
            raise CameraError(ERROR_AUTH_FAILED, "没拿到萤石云的访问令牌")
        return token

    def live_address(self, *, token: str, device_serial: str, channel: int) -> str:
        body = self._post(
            EZVIZ_LIVE_PATH,
            {"accessToken": token, "deviceSerial": device_serial, "channelNo": str(channel)},
        )
        url = body.get("url")
        if not isinstance(url, str) or not url:
            raise CameraError(ERROR_UNREACHABLE, "萤石云没给出可用的视频地址")
        return url


@dataclass(frozen=True, slots=True)
class RtspSource:
    """通用 RTSP/ONVIF 地址。"""

    url: str
    timeout_seconds: float = 15.0
    grabber: Grabber = grab_frame_from_url
    name: str = "rtsp"

    def fetch_frame(self) -> bytes:
        if not self.url.startswith(("rtsp://", "http://", "https://")):
            raise CameraError(ERROR_BAD_CONFIG, "地址要以 rtsp:// 开头")
        return self.grabber(self.url, timeout_seconds=self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class EzvizSource:
    """萤石云：先换 token / 取流地址，再抓一帧。"""

    api: EzvizApi
    app_key: str
    app_secret: str
    device_serial: str
    channel: int = DEFAULT_CHANNEL
    timeout_seconds: float = 15.0
    grabber: Grabber = grab_frame_from_url
    name: str = "ezviz"

    def fetch_frame(self) -> bytes:
        token = self.api.access_token(app_key=self.app_key, app_secret=self.app_secret)
        url = self.api.live_address(
            token=token, device_serial=self.device_serial, channel=self.channel
        )
        return self.grabber(url, timeout_seconds=self.timeout_seconds)


def build_camera_source(
    camera: Camera,
    secrets: dict[str, str],
    *,
    timeout_seconds: float = 15.0,
    ezviz_api: EzvizApi | None = None,
    grabber: Grabber = grab_frame_from_url,
) -> CameraSource:
    """按 provider 组装适配器；缺字段就抛 `bad_config`，调用方转成给用户看的话。"""
    if camera.provider == CAMERA_PROVIDER_RTSP:
        url = camera.config.get("url", "").strip()
        if not url:
            raise CameraError(ERROR_BAD_CONFIG, "还没填摄像头的地址")
        user = secrets.get("user", "")
        credential = secrets.get("credential", "")
        if user and credential and "://" in url:
            scheme, rest = url.split("://", 1)
            tail = rest.rsplit("@", 1)[-1]
            url = f"{scheme}://{quote(user)}:{quote(credential)}@{tail}"
        return RtspSource(url=url, timeout_seconds=timeout_seconds, grabber=grabber)

    if camera.provider == CAMERA_PROVIDER_EZVIZ:
        app_key = camera.config.get("app_key", "").strip()
        app_secret = secrets.get("app_secret", "").strip()
        serial = camera.config.get("device_serial", "").strip()
        if not (app_key and app_secret and serial):
            raise CameraError(ERROR_BAD_CONFIG, "萤石云还缺应用密钥或设备序列号")
        channel = int(camera.config.get("channel", DEFAULT_CHANNEL) or DEFAULT_CHANNEL)
        return EzvizSource(
            api=ezviz_api or HttpxEzvizApi(timeout_seconds=timeout_seconds),
            app_key=app_key,
            app_secret=app_secret,
            device_serial=serial,
            channel=channel,
            timeout_seconds=timeout_seconds,
            grabber=grabber,
        )

    raise CameraError(ERROR_BAD_CONFIG, f"不认识的摄像头类型: {camera.provider}")


__all__ = [
    "DEFAULT_CHANNEL",
    "EZVIZ_BASE_URL",
    "EZVIZ_LIVE_PATH",
    "EZVIZ_TOKEN_PATH",
    "EzvizApi",
    "EzvizSource",
    "Grabber",
    "HttpxEzvizApi",
    "RtspSource",
    "build_camera_source",
    "grab_frame_from_url",
]
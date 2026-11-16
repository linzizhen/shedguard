"""摄像头的领域模型与适配器契约。

只放纯逻辑：常量、数据类、错误分类、设备编号与脱敏规则。
真实取帧在 `infra/camera_sources.py`，调度在 `services/cameras.py`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Protocol

# 支持的视频源类型
CAMERA_PROVIDER_EZVIZ: Final = "ezviz"
CAMERA_PROVIDER_RTSP: Final = "rtsp"
CAMERA_PROVIDERS: Final = (CAMERA_PROVIDER_EZVIZ, CAMERA_PROVIDER_RTSP)

# 摄像头当前状态（给人看的那一层由 App 翻译成人话）
CAMERA_STATUS_OK: Final = "ok"
CAMERA_STATUS_AUTH_FAILED: Final = "auth_failed"
CAMERA_STATUS_UNREACHABLE: Final = "unreachable"
CAMERA_STATUS_NEVER_TESTED: Final = "never_tested"
CAMERA_STATUSES: Final = (
    CAMERA_STATUS_OK,
    CAMERA_STATUS_AUTH_FAILED,
    CAMERA_STATUS_UNREACHABLE,
    CAMERA_STATUS_NEVER_TESTED,
)

# 取帧失败的分类，与状态一一对应
ERROR_AUTH_FAILED: Final = "auth_failed"
ERROR_UNREACHABLE: Final = "unreachable"
ERROR_NO_FRAME: Final = "no_frame"
ERROR_BAD_CONFIG: Final = "bad_config"
FAILURE_KIND_TO_STATUS: Final = {
    ERROR_AUTH_FAILED: CAMERA_STATUS_AUTH_FAILED,
    ERROR_UNREACHABLE: CAMERA_STATUS_UNREACHABLE,
    ERROR_NO_FRAME: CAMERA_STATUS_UNREACHABLE,
    ERROR_BAD_CONFIG: CAMERA_STATUS_UNREACHABLE,
}

# 连续失败够数就发这条提醒（沿用 P17 的提醒通道）
ALERT_KIND_CAMERA_OFFLINE: Final = "camera_offline"
CAMERA_ALERT_TITLE: Final = "摄像头可能掉线了"
CAMERA_ALERT_BODY: Final = "有好几次没能从摄像头拿到画面，检查一下电源和网络。"

# 抓到的帧走现有图片流水线，device_id 用这个前缀拼摄像头 id
DEVICE_ID_PREFIX: Final = "camera-"

MAX_LABEL_LENGTH: Final = 64
MAX_CONFIG_KEYS: Final = 8
MAX_CONFIG_VALUE_LENGTH: Final = 512

DEFAULT_POLL_MINUTES: Final = 30
DEFAULT_TIMEOUT_SECONDS: Final = 15
DEFAULT_MAX_FAILURES: Final = 3

# 每种 provider 允许出现在配置里的键（含密码的键单独加密，不进 config_json）
ALLOWED_CONFIG_KEYS: Final = {
    CAMERA_PROVIDER_EZVIZ: frozenset({"device_serial", "channel", "app_key", "app_secret"}),
    CAMERA_PROVIDER_RTSP: frozenset({"url", "user", "credential"}),
}

# 这些键的取值要加密，不能留在 config_json 里
SECRET_CONFIG_KEYS: Final = {
    CAMERA_PROVIDER_EZVIZ: frozenset({"app_secret"}),
    CAMERA_PROVIDER_RTSP: frozenset({"user", "credential"}),
}


class CameraError(Exception):
    """取帧失败。

    `kind` 是机器可读的分类（见模块常量），`detail` 是直接能给用户看的一句话。
    """

    def __init__(self, kind: str, detail: str) -> None:
        if kind not in FAILURE_KIND_TO_STATUS:
            raise ValueError(f"未知的摄像头错误类型: {kind!r}")
        super().__init__(detail)
        self.kind = kind
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


class CameraSource(Protocol):
    """一个视频源只要能交出一张 JPEG，就能接进现有流水线。"""

    @property
    def name(self) -> str: ...

    def fetch_frame(self) -> bytes:
        """返回 JPEG 字节；失败必须抛 `CameraError`。"""
        ...


@dataclass(frozen=True, slots=True)
class Camera:
    id: str
    owner_id: str
    pet_id: str | None
    provider: str
    label: str
    config: dict[str, str] = field(default_factory=dict)
    secret_enc: str = ""
    enabled: bool = True
    status: str = CAMERA_STATUS_NEVER_TESTED
    last_error: str | None = None
    last_frame_at_utc: str | None = None
    consecutive_failures: int = 0
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("摄像头需要一个名字")
        if len(self.label) > MAX_LABEL_LENGTH:
            raise ValueError(f"名字不能超过 {MAX_LABEL_LENGTH} 个字符")
        if self.provider not in CAMERA_PROVIDERS:
            raise ValueError(f"不支持的摄像头类型: {self.provider!r}")
        if self.status not in CAMERA_STATUSES:
            raise ValueError(f"未知的摄像头状态: {self.status!r}")
        if self.consecutive_failures < 0:
            raise ValueError("连续失败次数不能是负数")

    @property
    def device_id(self) -> str:
        """进图片表时用的设备编号。"""
        return camera_device_id(self.id)


@dataclass(frozen=True, slots=True)
class CameraTestResult:
    ok: bool
    kind: str
    detail: str
    took_ms: int


def camera_device_id(camera_id: str) -> str:
    """`camera-<id>`，符合 `validate_device_id` 的 `[A-Za-z0-9_-]{1,64}`。"""
    return f"{DEVICE_ID_PREFIX}{camera_id}"


def camera_id_from_device_id(device_id: str) -> str | None:
    """反向解析；不是摄像头帧就返回 None。"""
    if not device_id.startswith(DEVICE_ID_PREFIX):
        return None
    rest = device_id[len(DEVICE_ID_PREFIX) :]
    return rest or None


def split_secret_config(
    provider: str, config: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """把配置拆成「可明文保存」与「必须加密」两份。

    未知 provider 直接报错，避免把不认识的键明文落库。
    """
    if provider not in CAMERA_PROVIDERS:
        raise ValueError(f"不支持的摄像头类型: {provider!r}")
    allowed = ALLOWED_CONFIG_KEYS[provider]
    secrets = SECRET_CONFIG_KEYS[provider]
    public: dict[str, str] = {}
    private: dict[str, str] = {}
    for key, value in config.items():
        if key not in allowed:
            raise ValueError(f"{provider} 不支持这个配置项: {key}")
        if len(value) > MAX_CONFIG_VALUE_LENGTH:
            raise ValueError(f"配置项 {key} 太长")
        if key in secrets:
            private[key] = value
        else:
            public[key] = value
    if len(public) + len(private) > MAX_CONFIG_KEYS:
        raise ValueError(f"配置项不能超过 {MAX_CONFIG_KEYS} 个")
    return public, private


def redact_config(provider: str, config: dict[str, str]) -> dict[str, str]:
    """给接口用：只回显白名单里的非敏感键，地址里的凭据打码。"""
    allowed = ALLOWED_CONFIG_KEYS.get(provider, frozenset())
    secrets = SECRET_CONFIG_KEYS.get(provider, frozenset())
    safe: dict[str, str] = {}
    for key, value in config.items():
        if key not in allowed or key in secrets:
            continue
        safe[key] = redact_rtsp_url(value) if key == "url" else value
    return safe


def redact_rtsp_url(url: str) -> str:
    """`rtsp://<用户名>:<密码>@<主机>/<路径>` → `rtsp://<用户名>:***@<主机>/<路径>`。"""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    credentials, tail = rest.rsplit("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{tail}"
    user, _ = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{tail}"


def status_for_failure(kind: str) -> str:
    return FAILURE_KIND_TO_STATUS.get(kind, CAMERA_STATUS_UNREACHABLE)


__all__ = [
    "ALERT_KIND_CAMERA_OFFLINE",
    "ALLOWED_CONFIG_KEYS",
    "CAMERA_ALERT_BODY",
    "CAMERA_ALERT_TITLE",
    "CAMERA_PROVIDERS",
    "CAMERA_PROVIDER_EZVIZ",
    "CAMERA_PROVIDER_RTSP",
    "CAMERA_STATUSES",
    "CAMERA_STATUS_AUTH_FAILED",
    "CAMERA_STATUS_NEVER_TESTED",
    "CAMERA_STATUS_OK",
    "CAMERA_STATUS_UNREACHABLE",
    "DEFAULT_MAX_FAILURES",
    "DEFAULT_POLL_MINUTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEVICE_ID_PREFIX",
    "ERROR_AUTH_FAILED",
    "ERROR_BAD_CONFIG",
    "ERROR_NO_FRAME",
    "ERROR_UNREACHABLE",
    "FAILURE_KIND_TO_STATUS",
    "Camera",
    "CameraError",
    "CameraSource",
    "CameraTestResult",
    "camera_device_id",
    "camera_id_from_device_id",
    "redact_config",
    "redact_rtsp_url",
    "split_secret_config",
    "status_for_failure",
]

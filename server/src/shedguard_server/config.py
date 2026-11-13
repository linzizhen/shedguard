"""应用配置：全部经 pydantic-settings 校验，非法值在启动时即失败。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_CAPTURE_HOUR = 20
DEFAULT_CAPTURE_WINDOW_MINUTES = 180
DEFAULT_DETECT_MIN_CONFIDENCE = 0.35
DEFAULT_BACKGROUND_DAYS = 7
DEFAULT_BASELINE_DAYS = 14
DEFAULT_MIN_BASELINE_SAMPLES = 7
DEFAULT_ROBUST_Z_THRESHOLD = 2.0
DEFAULT_ALERT_MIN_SIGNALS = 2
DEFAULT_ALERT_CONSECUTIVE_DAYS = 2
DEFAULT_STATE_MIN_CONFIDENCE = 0.6
DEFAULT_STATE_CROP_PADDING = 0.08
DEFAULT_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEFAULT_PUSH_TIMEOUT_SECONDS = 5.0
DEFAULT_ALERT_COOLDOWN_HOURS = 24
DEFAULT_IMAGE_RETENTION_DAYS = 0
DEFAULT_RATE_LIMIT_PER_MINUTE = 0
DEFAULT_RATE_LIMIT_BURST = 60


class Settings(BaseSettings):
    """服务配置，来源优先级：构造参数 > 环境变量 > .env 文件 > 缺省值。"""

    model_config = SettingsConfigDict(
        env_prefix="SHEDGUARD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("./data")
    db_url: str | None = None
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    max_upload_bytes: int = Field(default=DEFAULT_MAX_UPLOAD_BYTES, gt=0)
    timezone: str = DEFAULT_TIMEZONE
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    capture_hour: int = Field(default=DEFAULT_CAPTURE_HOUR, ge=0, le=23)
    capture_window_minutes: int = Field(default=DEFAULT_CAPTURE_WINDOW_MINUTES, ge=0, le=720)
    detector_model: str = ""
    detect_min_confidence: float = Field(
        default=DEFAULT_DETECT_MIN_CONFIDENCE, ge=0.0, le=1.0
    )
    background_days: int = Field(default=DEFAULT_BACKGROUND_DAYS, ge=1, le=60)
    baseline_days: int = Field(default=DEFAULT_BASELINE_DAYS, ge=3, le=90)
    min_baseline_samples: int = Field(default=DEFAULT_MIN_BASELINE_SAMPLES, ge=3, le=90)
    robust_z_threshold: float = Field(default=DEFAULT_ROBUST_Z_THRESHOLD, ge=1.0, le=6.0)
    alert_min_signals: int = Field(default=DEFAULT_ALERT_MIN_SIGNALS, ge=1, le=6)
    alert_consecutive_days: int = Field(default=DEFAULT_ALERT_CONSECUTIVE_DAYS, ge=1, le=7)
    state_model: str = ""
    state_min_confidence: float = Field(
        default=DEFAULT_STATE_MIN_CONFIDENCE, ge=0.0, le=1.0
    )
    state_crop_padding: float = Field(
        default=DEFAULT_STATE_CROP_PADDING, ge=0.0, le=0.3
    )
    auto_process: bool = True
    push_enabled: bool = True
    expo_push_url: str = DEFAULT_EXPO_PUSH_URL
    push_timeout_seconds: float = Field(default=DEFAULT_PUSH_TIMEOUT_SECONDS, gt=0.0, le=60.0)
    alert_cooldown_hours: int = Field(default=DEFAULT_ALERT_COOLDOWN_HOURS, ge=0, le=168)
    # 鉴权：默认开启；关闭后所有请求视为同一个本机账号（仅用于本地测试/开发）。
    auth_enabled: bool = True
    # 固件上传用的静态设备令牌；为空则不校验设备身份并记 WARNING。
    device_token: str = ""
    # 允许跨域的来源，逗号分隔；"*" 表示全部。为空则不加 CORS 头（生产默认）。
    # 仅网页版调试/局域网演示时设为 "*"。
    cors_origins: str = ""
    # 设备健康兜底扫描：离线或连续未检出时生成提醒。
    health_monitor_enabled: bool = True
    health_scan_minutes: int = Field(default=10, ge=1, le=1440)
    device_silence_hours: int = Field(default=6, ge=1, le=48)
    no_detection_streak: int = Field(default=5, ge=2, le=20)
    # 设备的活跃抓拍时段；静默提醒只在这个时段内判定。
    capture_start_hour: int = Field(default=8, ge=0, le=23)
    capture_end_hour: int = Field(default=20, ge=0, le=23)
    # 照片保留：0 表示永久保留（保持原行为）；大于 0 时后台按天清理过期图片。
    image_retention_days: int = Field(default=DEFAULT_IMAGE_RETENTION_DAYS, ge=0, le=3650)
    # 请求速率限制：0 表示关闭；开启后按「客户端 IP + 令牌摘要」分组限流。
    rate_limit_per_minute: int = Field(default=DEFAULT_RATE_LIMIT_PER_MINUTE, ge=0, le=6000)
    rate_limit_burst: int = Field(default=DEFAULT_RATE_LIMIT_BURST, ge=1, le=6000)
    # 萌照：每天挑一张近景发出来；开关关掉时后台不扫描，接口照常可读。
    portrait_enabled: bool = True
    portrait_scan_minutes: int = Field(default=10, ge=1, le=1440)
    portrait_min_subject_ratio: float = Field(default=0.10, ge=0.0, le=1.0)
    portrait_min_detector_confidence: float = Field(default=0.45, ge=0.0, le=1.0)
    portrait_max_output_px: int = Field(default=640, ge=128, le=2048)
    portrait_jpeg_quality: int = Field(default=88, ge=40, le=100)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"无法识别的时区: {value!r}"
            raise ValueError(msg) from exc
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            msg = f"日志级别必须是 {sorted(allowed)} 之一，收到 {value!r}"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _derive_db_url(self) -> Settings:
        if self.db_url is None:
            db_path = self.data_dir / "shedguard.db"
            self.db_url = f"sqlite:///{db_path.as_posix()}"
        return self

    @property
    def resolved_db_url(self) -> str:
        """已派生完成的数据库连接串。"""
        if self.db_url is None:  # pragma: no cover - 构造后不可能为 None
            msg = "db_url 未初始化"
            raise RuntimeError(msg)
        return self.db_url

    @property
    def cors_origin_list(self) -> list[str]:
        """解析后的允许来源列表；空表示不启用 CORS。"""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
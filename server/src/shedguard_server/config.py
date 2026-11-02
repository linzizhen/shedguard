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
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
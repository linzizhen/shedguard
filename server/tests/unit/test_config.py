"""配置项缺省值、环境变量覆盖与非法值拒绝。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from shedguard_server.config import Settings


def test_defaults_when_no_env(workdir: Path) -> None:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.timezone == "Asia/Shanghai"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    monkeypatch.setenv("SHEDGUARD_HOST", "0.0.0.0")
    monkeypatch.setenv("SHEDGUARD_PORT", "9001")
    monkeypatch.setenv("SHEDGUARD_MAX_UPLOAD_BYTES", "2048")
    monkeypatch.setenv("SHEDGUARD_LOG_FORMAT", "console")

    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.host == "0.0.0.0"
    assert settings.port == 9001
    assert settings.max_upload_bytes == 2048
    assert settings.log_format == "console"


@pytest.mark.parametrize("port", ["0", "65536", "-1", "not-a-number"])
def test_invalid_port_rejected(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("SHEDGUARD_PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_timezone_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHEDGUARD_TIMEZONE", "Mars/Olympus")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_log_format_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHEDGUARD_LOG_FORMAT", "xml")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_db_url_derived_from_data_dir(workdir: Path) -> None:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.db_url is not None
    assert settings.db_url.startswith("sqlite:///")
    assert settings.db_url.endswith("shedguard.db")
    assert workdir.as_posix() in settings.db_url


def test_tzinfo_and_resolved_db_url(workdir: Path) -> None:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert str(settings.tzinfo) == "Asia/Shanghai"
    assert settings.resolved_db_url == settings.db_url


def test_explicit_db_url_not_overridden(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    monkeypatch.setenv("SHEDGUARD_DB_URL", "sqlite:///:memory:")

    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.db_url == "sqlite:///:memory:"


def test_capture_defaults(workdir: Path) -> None:
    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.capture_hour == 20
    assert settings.capture_window_minutes == 180


def test_capture_env_override(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    monkeypatch.setenv("SHEDGUARD_CAPTURE_HOUR", "19")
    monkeypatch.setenv("SHEDGUARD_CAPTURE_WINDOW_MINUTES", "90")

    settings = Settings(_env_file=None, data_dir=workdir)  # type: ignore[call-arg]

    assert settings.capture_hour == 19
    assert settings.capture_window_minutes == 90


@pytest.mark.parametrize("hour", ["24", "-1", "not-a-number"])
def test_invalid_capture_hour_rejected(monkeypatch: pytest.MonkeyPatch, hour: str) -> None:
    monkeypatch.setenv("SHEDGUARD_CAPTURE_HOUR", hour)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize("minutes", ["721", "-1", "not-a-number"])
def test_invalid_capture_window_rejected(
    monkeypatch: pytest.MonkeyPatch,
    minutes: str,
) -> None:
    monkeypatch.setenv("SHEDGUARD_CAPTURE_WINDOW_MINUTES", minutes)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
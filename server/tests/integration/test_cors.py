"""CORS 开关的集成测试（网页版调试需要跨域）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from shedguard_server.app import create_app
from shedguard_server.config import Settings

ORIGIN = "http://10.0.0.2:8083"


def _settings(workdir: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "data_dir": workdir / "data",
        "db_url": None,
        "auth_enabled": False,
        "health_monitor_enabled": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_cors_enabled_adds_header(workdir: Path) -> None:
    app = create_app(_settings(workdir, cors_origins="*"))
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "*"
    app.state.engine.dispose()


def test_cors_disabled_by_default(workdir: Path) -> None:
    app = create_app(_settings(workdir))
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers
    app.state.engine.dispose()

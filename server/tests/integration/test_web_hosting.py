"""前端构建产物托管（一个地址既是界面也是接口）的集成测试。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shedguard_server.app import _resolve_within, create_app
from shedguard_server.config import Settings

INDEX_HTML = '<!doctype html><div id="root">ShedGuard</div>'


def _settings(workdir: Path, web_dir: str = "") -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=workdir / "data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        auth_enabled=False,
        health_monitor_enabled=False,
        portrait_enabled=False,
        contribution_enabled=False,
        web_dir=web_dir,
    )


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "_expo" / "static" / "js" / "web").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "_expo" / "static" / "js" / "web" / "entry-abc123.js").write_text(
        "console.log(2)", encoding="utf-8"
    )
    return dist


@pytest.fixture()
def client(workdir: Path) -> Iterator[TestClient]:
    app = create_app(_settings(workdir, str(_make_dist(workdir))))
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


@pytest.fixture()
def bare_client(workdir: Path) -> Iterator[TestClient]:
    """没配前端目录、也没构建产物：行为必须与托管前完全一致。"""
    app = create_app(_settings(workdir, str(workdir / "nowhere")))
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


class TestHosting:
    def test_index_at_root_is_not_cached(self, client: TestClient) -> None:
        response = client.get("/")

        assert response.status_code == 200
        assert "ShedGuard" in response.text
        assert response.headers["cache-control"] == "no-cache"

    def test_client_route_falls_back_to_index(self, client: TestClient) -> None:
        # /log 是前端路由，磁盘上没有这个文件，必须回 index.html 交给前端接管。
        response = client.get("/log")

        assert response.status_code == 200
        assert "ShedGuard" in response.text

    def test_asset_is_cached_forever(self, client: TestClient) -> None:
        response = client.get("/assets/index-abc123.js")

        assert response.status_code == 200
        assert response.text == "console.log(1)"
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_expo_bundle_is_cached_forever(self, client: TestClient) -> None:
        # expo export 的打包脚本在 _expo/static/js 下，文件名同样带内容哈希。
        response = client.get("/_expo/static/js/web/entry-abc123.js")

        assert response.status_code == 200
        assert response.text == "console.log(2)"
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_other_files_are_not_cached(self, client: TestClient) -> None:
        # dist 里没有 favicon.ico，会回落到 index.html —— 回落的页面绝不能长缓存，
        # 否则发版后手机还拿着旧壳子。
        response = client.get("/favicon.ico")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"


class TestApiStillWins:
    def test_unknown_api_path_stays_json_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/does-not-exist")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_health_stays_json(self, client: TestClient) -> None:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_business_route_is_untouched(self, client: TestClient) -> None:
        response = client.get("/api/v1/pets")

        assert response.status_code == 200
        assert "items" in response.json()

    def test_docs_is_not_swallowed(self, client: TestClient) -> None:
        response = client.get("/docs")

        assert response.status_code == 200
        assert "swagger" in response.text.lower()


class TestWithoutWebDir:
    def test_root_returns_404(self, bare_client: TestClient) -> None:
        response = bare_client.get("/")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_api_still_works(self, bare_client: TestClient) -> None:
        assert bare_client.get("/api/v1/pets").status_code == 200


class TestPathSafety:
    def test_resolve_within_rejects_escape(self, workdir: Path) -> None:
        root = workdir / "dist"
        root.mkdir()
        (workdir / "secret.txt").write_text("nope", encoding="utf-8")

        assert _resolve_within(root, "../secret.txt") is None

    def test_resolve_within_accepts_plain_file(self, workdir: Path) -> None:
        root = workdir / "dist"
        root.mkdir()
        target = root / "a.txt"
        target.write_text("ok", encoding="utf-8")

        assert _resolve_within(root, "a.txt") == target
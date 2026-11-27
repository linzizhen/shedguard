"""输入质量门的集成测试：走真实的 check-photo 链路。

这个文件自己装配 app（不共用 `client` fixture），因为质量门默认关闭，
这里需要把它打开。纯色块与棋盘格都用程序生成，不依赖外部数据。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from shedguard_server.app import create_app
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction

PETS = "/api/v1/pets"
SIZE = 96


def make_jpeg(pixels: np.ndarray) -> bytes:
    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    return encoded.tobytes()


def solid(value: int = 180) -> np.ndarray:
    return np.full((SIZE, SIZE, 3), value, dtype=np.uint8)


def checker(cell: int = 8) -> np.ndarray:
    """亮暗棋盘格：有真实边缘，能通过清晰度门。

    亮格取 230 而不是 255 —— 255 会占掉一半像素，直接被过曝门拦下。
    """
    pixels = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    rows = np.arange(SIZE) // cell
    cols = np.arange(SIZE) // cell
    mask = (rows[:, None] + cols[None, :]) % 2 == 0
    pixels[mask] = 230
    pixels[~mask] = 40
    return pixels


class _FakeClassifier:
    """固定输出 shedding 的分类器替身。"""

    @property
    def name(self) -> str:
        return "fake-classifier"

    def classify(self, _frame: ImageFrame) -> StatePrediction:
        return StatePrediction(
            state=ShedState.SHEDDING,
            confidence=0.9,
            probabilities={"normal": 0.05, "opaque": 0.05, "shedding": 0.9},
        )


class _BlindDetector:
    """永远找不到守宫，用来测 `no_subject`。"""

    @property
    def name(self) -> str:
        return "blind-detector"

    def detect(self, _frame: ImageFrame) -> Detection | None:
        return None


def _settings(workdir: Path, *, gate: bool) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=workdir / "data",
        db_url=None,
        timezone="Asia/Shanghai",
        log_level="INFO",
        log_format="json",
        max_upload_bytes=1024 * 1024,
        auth_enabled=False,
        health_monitor_enabled=False,
        portrait_enabled=False,
        contribution_enabled=False,
        auto_process=False,
        quality_gate_enabled=gate,
    )


def _client(workdir: Path, *, gate: bool) -> Iterator[TestClient]:
    app = create_app(_settings(workdir, gate=gate))
    with TestClient(app) as test_client:
        test_client.app.state.state_classifier = _FakeClassifier()  # type: ignore[attr-defined]
        yield test_client
    engine: Engine = app.state.engine
    engine.dispose()


@pytest.fixture()
def gated(workdir: Path) -> Iterator[TestClient]:
    """质量门打开。"""
    yield from _client(workdir, gate=True)


@pytest.fixture()
def ungated(workdir: Path) -> Iterator[TestClient]:
    """质量门关闭（默认行为）。"""
    yield from _client(workdir, gate=False)


def _pet(client: TestClient) -> str:
    response = cast(
        httpx.Response,
        client.post(PETS, json={"name": "小橙", "species": "豹纹守宫"}),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _check(client: TestClient, pet_id: str, pixels: np.ndarray) -> dict[str, object]:
    response = cast(
        httpx.Response,
        client.post(
            f"{PETS}/{pet_id}/check-photo",
            files={"file": ("a.jpg", make_jpeg(pixels), "image/jpeg")},
        ),
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


class TestGateRejects:
    """门打开时，看不清的图必须被拒，并且给出具体原因。"""

    def test_solid_color_is_too_blurry(self, gated: TestClient) -> None:
        body = _check(gated, _pet(gated), solid())

        assert body["state"] == "unknown"
        assert body["quality_reason"] == "too_blurry"
        assert body["confidence"] is None
        assert body["probabilities"] is None
        assert "糊" in str(body["advice"])

    def test_dark_texture_is_too_dark(self, gated: TestClient) -> None:
        """把棋盘格整体压暗：边缘还在（清晰度够），但整体亮度低于 18。

        注意别写成两次连续的条件赋值（先 230→60，再把 <=100 全归零会把 60 也吃掉），
        那样得到的是一张纯黑图，测的就变成清晰度门了。
        """
        pixels = np.where(checker() > 100, 60, 0).astype(np.uint8)
        body = _check(gated, _pet(gated), pixels)

        assert body["state"] == "unknown"
        assert body["quality_reason"] == "too_dark"
        assert "暗" in str(body["advice"])

    def test_blown_out_is_overexposed(self, gated: TestClient) -> None:
        pixels = checker()
        pixels[: SIZE * 3 // 4, :] = 255
        body = _check(gated, _pet(gated), pixels)

        assert body["state"] == "unknown"
        assert body["quality_reason"] == "overexposed"
        assert "亮" in str(body["advice"])

    def test_no_detection_is_no_subject(self, gated: TestClient) -> None:
        gated.app.state.detector = _BlindDetector()  # type: ignore[attr-defined]
        body = _check(gated, _pet(gated), checker())

        assert body["state"] == "unknown"
        assert body["quality_reason"] == "no_subject"
        assert "没找到" in str(body["advice"])


class TestGatePasses:
    """有纹理、亮度正常的图照常走分类器。"""

    def test_textured_photo_passes(self, gated: TestClient) -> None:
        body = _check(gated, _pet(gated), checker())

        assert body["state"] == "shedding"
        assert body["quality_reason"] is None
        assert body["confidence"] == pytest.approx(0.9, abs=1e-4)


class TestGateOff:
    """门关闭时行为与加门之前完全一致。"""

    def test_solid_color_still_classified(self, ungated: TestClient) -> None:
        body = _check(ungated, _pet(ungated), solid())

        assert body["state"] == "shedding"
        assert body["quality_reason"] is None
        assert body["confidence"] == pytest.approx(0.9, abs=1e-4)

    def test_no_detection_has_no_reason(self, ungated: TestClient) -> None:
        ungated.app.state.detector = _BlindDetector()  # type: ignore[attr-defined]
        body = _check(ungated, _pet(ungated), checker())

        assert body["state"] == "unknown"
        assert body["quality_reason"] is None


class TestGateStateVersion:
    """判定规则变了，缓存版本必须跟着变，否则旧结论会一直留着。"""

    def test_state_version_is_bumped(self, gated: TestClient) -> None:
        from shedguard_server.services.shedding import STATE_VERSION

        assert STATE_VERSION == "2"

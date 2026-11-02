"""ONNX 检测器的单元测试，用假会话替代真实推理。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.errors import StorageUnavailableError
from shedguard_server.infra.detector import INPUT_SIZE, OnnxDetector

ANCHORS = 8400


class _FakeSession:
    def __init__(self, outputs: list[Any]) -> None:
        self._outputs = outputs
        self.feeds: list[dict[str, Any]] = []

    def run(self, output_names: Any, feed_dict: dict[str, Any]) -> list[Any]:
        del output_names
        self.feeds.append(feed_dict)
        return self._outputs


def _predictions(
    *,
    center_x: float = 320.0,
    center_y: float = 320.0,
    width: float = 100.0,
    height: float = 80.0,
    score: float = 0.9,
) -> np.ndarray:
    tensor = np.zeros((1, 5, ANCHORS), dtype=np.float32)
    tensor[0, 0, 0] = center_x
    tensor[0, 1, 0] = center_y
    tensor[0, 2, 0] = width
    tensor[0, 3, 0] = height
    tensor[0, 4, 0] = score
    return tensor


def _frame(width: int, height: int) -> ImageFrame:
    return ImageFrame(
        width=width, height=height, rgb=np.zeros((height, width, 3), dtype=np.uint8)
    )


def _detector(session: _FakeSession) -> OnnxDetector:
    return OnnxDetector(session=session, input_name="images", name="fake")


def test_detect_maps_box_back_to_original_size() -> None:
    detector = _detector(_FakeSession([_predictions()]))

    found = detector.detect(_frame(640, 640))

    assert found is not None
    assert found.box == (270, 280, 370, 360)
    assert found.confidence == pytest.approx(0.9)


def test_detect_undoes_letterbox_padding() -> None:
    detector = _detector(_FakeSession([_predictions()]))

    found = detector.detect(_frame(320, 240))

    assert found is not None
    assert found.box == (135, 100, 185, 140)


def test_detect_returns_none_below_confidence() -> None:
    detector = _detector(_FakeSession([_predictions(score=0.1)]))

    assert detector.detect(_frame(640, 640)) is None


def test_detect_returns_none_on_empty_output() -> None:
    detector = _detector(_FakeSession([]))

    assert detector.detect(_frame(64, 64)) is None


def test_detect_accepts_transposed_predictions() -> None:
    tensor = _predictions()[0].T[np.newaxis, ...]
    detector = _detector(_FakeSession([tensor]))

    found = detector.detect(_frame(640, 640))

    assert found is not None
    assert found.box == (270, 280, 370, 360)


def test_detect_feeds_square_tensor() -> None:
    session = _FakeSession([_predictions()])
    detector = _detector(session)

    detector.detect(_frame(320, 240))

    feed = session.feeds[0]["images"]
    assert feed.shape == (1, 3, INPUT_SIZE, INPUT_SIZE)


def test_from_path_requires_existing_file(workdir: Path) -> None:
    with pytest.raises(StorageUnavailableError, match="检测模型不存在"):
        OnnxDetector.from_path(workdir / "missing.onnx")
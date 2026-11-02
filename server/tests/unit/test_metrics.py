"""体表信号指标的单元测试。"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.metrics import compute_metrics, lstar_to_luminance

BODY_BOX = Detection(x1=8, y1=8, x2=56, y2=56, confidence=0.9)


def solid_frame(width: int, height: int, rgb: tuple[int, int, int]) -> ImageFrame:
    pixels = np.full((height, width, 3), rgb, dtype=np.uint8)
    return ImageFrame(width=width, height=height, rgb=pixels)


def test_image_frame_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="不一致"):
        ImageFrame(width=10, height=10, rgb=np.zeros((5, 5, 3), dtype=np.uint8))


def test_white_frame_has_max_lightness() -> None:
    metrics = compute_metrics(solid_frame(64, 64, (255, 255, 255)), BODY_BOX)

    assert metrics.lightness_mean == pytest.approx(100.0, abs=0.01)
    assert metrics.high_light_ratio == pytest.approx(1.0)


def test_black_frame_has_zero_lightness() -> None:
    metrics = compute_metrics(solid_frame(64, 64, (0, 0, 0)), BODY_BOX)

    assert metrics.lightness_mean == pytest.approx(0.0, abs=0.01)
    assert metrics.high_light_ratio == pytest.approx(0.0)


def test_uniform_frame_has_no_edges_and_no_hue_spread() -> None:
    metrics = compute_metrics(solid_frame(64, 64, (120, 120, 120)), BODY_BOX)

    assert metrics.edge_density == pytest.approx(0.0)
    assert metrics.color_entropy == pytest.approx(0.0)


def test_brighter_frame_increases_lightness() -> None:
    base = compute_metrics(solid_frame(64, 64, (128, 120, 110)), BODY_BOX)
    brighter = compute_metrics(solid_frame(64, 64, (140, 132, 121)), BODY_BOX)

    assert brighter.lightness_mean > base.lightness_mean


def test_desaturated_frame_has_lower_saturation() -> None:
    colorful = compute_metrics(solid_frame(64, 64, (200, 120, 60)), BODY_BOX)
    grayish = compute_metrics(solid_frame(64, 64, (160, 140, 120)), BODY_BOX)

    assert grayish.saturation_mean < colorful.saturation_mean


def test_exposure_scale_darkens_pixels() -> None:
    frame = solid_frame(64, 64, (180, 180, 180))

    plain = compute_metrics(frame, BODY_BOX)
    compensated = compute_metrics(frame, BODY_BOX, exposure_scale=2.0)

    assert compensated.lightness_mean < plain.lightness_mean


def test_background_lightness_excludes_body_box() -> None:
    pixels = np.zeros((64, 64, 3), dtype=np.uint8)
    pixels[:, 32:] = 255
    frame = ImageFrame(width=64, height=64, rgb=pixels)
    detection = Detection(x1=32, y1=0, x2=64, y2=64, confidence=1.0)

    metrics = compute_metrics(frame, detection)

    assert metrics.background_lightness == pytest.approx(0.0, abs=0.01)
    assert metrics.lightness_mean > 90.0


def test_detection_rejects_inverted_box() -> None:
    with pytest.raises(ValueError, match="检测框无效"):
        Detection(x1=10, y1=10, x2=5, y2=20, confidence=0.5)


def test_detection_area() -> None:
    detection = Detection(x1=10, y1=20, x2=40, y2=60, confidence=0.8)

    assert detection.box == (10, 20, 40, 60)
    assert detection.area == 30 * 40


def test_lstar_to_luminance_hits_bounds() -> None:
    assert lstar_to_luminance(100.0) == pytest.approx(1.0, abs=0.01)
    assert lstar_to_luminance(0.0) == pytest.approx(0.0, abs=0.001)


def test_lstar_to_luminance_is_monotonic() -> None:
    values = [lstar_to_luminance(value) for value in (20.0, 40.0, 60.0, 80.0)]

    assert values == sorted(values)
    assert all(later > earlier for earlier, later in itertools.pairwise(values))
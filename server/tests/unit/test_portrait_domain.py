"""萌照选片纯函数的单元测试。"""

from __future__ import annotations

from datetime import date

import cv2
import numpy as np
import pytest

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.portrait import (
    Candidate,
    box_area,
    center_score,
    crop_square,
    difference_hash,
    encode_square,
    hash_distance,
    is_near_duplicate,
    passes_thresholds,
    portrait_rel_path,
    rank_candidates,
    square_crop_box,
    subject_ratio,
)


def _candidate(
    image_id: str = "img-1",
    *,
    box: tuple[int, int, int, int] | None = (100, 100, 300, 300),
    confidence: float | None = 0.9,
    edge: float | None = 50.0,
    highlight: float | None = 0.05,
    width: int = 640,
    height: int = 480,
) -> Candidate:
    return Candidate(
        image_id=image_id,
        box=box,
        detector_confidence=confidence,
        edge_density=edge,
        high_light_ratio=highlight,
        width=width,
        height=height,
    )


def _frame(width: int = 64, height: int = 48, *, bright_block: bool = False) -> ImageFrame:
    if bright_block:
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[height // 8 : height // 2, width // 4 : width // 2] = 240
    else:
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
    return ImageFrame(width=width, height=height, rgb=rgb)


class TestGeometry:
    def test_box_area_and_ratio(self) -> None:
        assert box_area((0, 0, 10, 20)) == 200
        assert subject_ratio((0, 0, 320, 240), 640, 480) == pytest.approx(0.25)

    def test_ratio_guards_zero_dimensions(self) -> None:
        assert subject_ratio((0, 0, 10, 10), 0, 480) == 0.0

    def test_center_score_is_one_at_center(self) -> None:
        assert center_score((270, 190, 370, 290), 640, 480) == pytest.approx(1.0)

    def test_center_score_lower_when_off_center(self) -> None:
        centered = center_score((270, 190, 370, 290), 640, 480)
        corner = center_score((0, 0, 100, 100), 640, 480)
        assert corner < centered
        assert 0.0 <= corner < 1.0


class TestThresholds:
    def test_full_frame_candidate_passes(self) -> None:
        assert passes_thresholds(_candidate())

    def test_missing_box_fails(self) -> None:
        assert not passes_thresholds(_candidate(box=None))

    def test_low_confidence_fails(self) -> None:
        assert not passes_thresholds(_candidate(confidence=0.2))

    def test_small_subject_fails(self) -> None:
        assert not passes_thresholds(_candidate(box=(0, 0, 20, 20)))

    def test_glare_fails(self) -> None:
        assert not passes_thresholds(_candidate(highlight=0.9))

    def test_missing_confidence_fails(self) -> None:
        assert not passes_thresholds(_candidate(confidence=None))


class TestRanking:
    def test_empty_input_returns_empty(self) -> None:
        assert rank_candidates([]) == []

    def test_prefers_larger_subject(self) -> None:
        small = _candidate("small", box=(250, 160, 450, 360), edge=50.0)
        large = _candidate("large", box=(170, 90, 470, 390), edge=50.0)
        ranked = rank_candidates([small, large])
        assert [item.candidate.image_id for item in ranked] == ["large", "small"]

    def test_drops_blurry_outliers_relative_to_median(self) -> None:
        sharp = [_candidate(f"s{n}", edge=60.0) for n in range(3)]
        blurry = _candidate("blurry", edge=5.0)
        ranked = rank_candidates([*sharp, blurry])
        assert "blurry" not in {item.candidate.image_id for item in ranked}

    def test_keeps_some_when_all_are_equally_soft(self) -> None:
        soft = [_candidate(f"s{n}", edge=8.0) for n in range(3)]
        assert len(rank_candidates(soft)) == 3

    def test_all_filtered_returns_empty(self) -> None:
        assert rank_candidates([_candidate(box=None), _candidate(confidence=0.1)]) == []

    def test_scores_are_bounded(self) -> None:
        ranked = rank_candidates([_candidate(edge=100.0)])
        assert 0.0 <= ranked[0].score <= 1.0


class TestSquareCrop:
    def test_returns_square_inside_frame(self) -> None:
        x1, y1, x2, y2 = square_crop_box((200, 100, 400, 300), 640, 480)
        assert (x2 - x1) == (y2 - y1)
        assert 0 <= x1 < x2 <= 640
        assert 0 <= y1 < y2 <= 480

    def test_clamps_at_left_edge(self) -> None:
        x1, _, x2, _ = square_crop_box((0, 200, 40, 260), 640, 480)
        assert x1 == 0
        assert x2 > x1

    def test_never_exceeds_short_side(self) -> None:
        x1, y1, x2, y2 = square_crop_box((0, 0, 640, 480), 640, 480)
        assert (x2 - x1) == (y2 - y1) == 480
        assert y1 == 0

    def test_crop_square_shape(self) -> None:
        cropped = crop_square(_frame(64, 48), (8, 8, 48, 48))
        assert (cropped.width, cropped.height) == (40, 40)
        assert cropped.rgb.shape == (40, 40, 3)

    def test_crop_square_rejects_empty_region(self) -> None:
        with pytest.raises(ValueError, match="裁剪区域无效"):
            crop_square(_frame(), (10, 10, 10, 10))


class TestHashing:
    def test_hash_is_16_hex_chars(self) -> None:
        digest = difference_hash(_frame(bright_block=True))
        assert len(digest) == 16
        int(digest, 16)

    def test_identical_frames_match(self) -> None:
        left = difference_hash(_frame(bright_block=True))
        right = difference_hash(_frame(bright_block=True))
        assert hash_distance(left, right) == 0
        assert is_near_duplicate(left, right)

    def test_different_frames_differ(self) -> None:
        left = difference_hash(_frame(bright_block=True))
        right = difference_hash(_frame())
        assert hash_distance(left, right) > 0

    def test_near_duplicate_threshold(self) -> None:
        assert is_near_duplicate("0000000000000000", "0000000000000001")
        assert not is_near_duplicate("0000000000000000", "ffffffffffffffff")


class TestPathsAndEncoding:
    def test_rel_path_layout(self) -> None:
        assert (
            portrait_rel_path(date(2026, 11, 13), "gecko-eye-01", "shot-1")
            == "portraits/2026-11-13/gecko-eye-01/shot-1.jpg"
        )

    def test_encode_square_is_decodable_jpeg(self) -> None:
        payload = encode_square(_frame(120, 90, bright_block=True), output_px=64, quality=88)
        decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None
        assert decoded.shape[:2] == (64, 64)
        assert decoded.dtype == np.uint8
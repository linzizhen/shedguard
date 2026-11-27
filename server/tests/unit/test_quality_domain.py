"""输入质量门的单元测试。

用合成图构造四种情形，不依赖任何外部数据：
纯色块（拉普拉斯方差恒为 0）、棋盘格（有纹理）、压暗的棋盘格、大片削顶白斑。
"""

from __future__ import annotations

import numpy as np

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.quality import (
    MEASURE_SIZE,
    QualityReason,
    evaluate_quality,
    measure_quality,
)


def solid_frame(value: int, size: int = MEASURE_SIZE) -> ImageFrame:
    pixels = np.full((size, size, 3), value, dtype=np.uint8)
    return ImageFrame(width=size, height=size, rgb=pixels)


def checker_frame(size: int = MEASURE_SIZE, cell: int = 8) -> ImageFrame:
    """亮暗棋盘格：有真实边缘，能通过清晰度门。

    亮格取 230 而不是 255 —— 255 会占掉一半像素，直接被过曝门拦下。
    """
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    rows = np.arange(size) // cell
    cols = np.arange(size) // cell
    mask = (rows[:, None] + cols[None, :]) % 2 == 0
    pixels[mask] = 230
    pixels[~mask] = 40
    return ImageFrame(width=size, height=size, rgb=pixels)


def test_solid_color_is_blurry() -> None:
    """纯色块的拉普拉斯方差是 0，必须被判为太糊。

    这条是质量门存在的意义：现有测试大量用纯色块当上传图，
    一旦开门它们全都该被拒。
    """
    verdict = evaluate_quality(solid_frame(180))

    assert verdict.reason is QualityReason.TOO_BLURRY
    assert verdict.metrics is not None
    assert verdict.metrics.sharpness == 0.0


def test_checkerboard_passes() -> None:
    """有纹理的图不该被任何一条门拦下。"""
    verdict = evaluate_quality(checker_frame())

    assert verdict.reason is None
    assert verdict.metrics is not None
    assert verdict.metrics.sharpness > 25.0


def test_dark_frame_is_reported_as_dark() -> None:
    """纹理够但整体很暗：先过清晰度，再被亮度拦下。"""
    pixels = checker_frame().rgb.astype(np.int16)
    dimmed = np.clip(pixels // 12, 0, 255).astype(np.uint8)
    frame = ImageFrame(width=MEASURE_SIZE, height=MEASURE_SIZE, rgb=dimmed)

    verdict = evaluate_quality(frame)

    assert verdict.reason is QualityReason.TOO_DARK
    assert verdict.metrics is not None
    assert verdict.metrics.lightness < 18.0


def test_overexposed_frame_is_reported_as_overexposed() -> None:
    """大半画面削顶到 255：清晰度与亮度都够，但细节已经丢了。"""
    pixels = checker_frame().rgb.copy()
    pixels[: MEASURE_SIZE * 3 // 4, :] = 255
    frame = ImageFrame(width=MEASURE_SIZE, height=MEASURE_SIZE, rgb=pixels)

    verdict = evaluate_quality(frame)

    assert verdict.reason is QualityReason.OVEREXPOSED
    assert verdict.metrics is not None
    assert verdict.metrics.saturated > 0.20


def test_measure_is_resolution_independent() -> None:
    """非 224 的输入会先缩放再量，不因为原图大小改变判定。"""
    small = checker_frame(size=112, cell=4)
    metrics = measure_quality(small)

    assert metrics.sharpness > 25.0
    assert 0.0 <= metrics.saturated <= 1.0


def test_thresholds_are_injectable() -> None:
    """阈值由调用方传入，抬高清晰度门槛能把棋盘格也拒掉。"""
    verdict = evaluate_quality(checker_frame(), min_sharpness=1_000_000.0)

    assert verdict.reason is QualityReason.TOO_BLURRY


def test_metrics_kept_even_when_passing() -> None:
    """通过的图也保留指标，日志与接口才能说清「差多少」。"""
    verdict = evaluate_quality(checker_frame())

    assert verdict.reason is None
    assert verdict.metrics is not None
    assert verdict.metrics.lightness > 0.0

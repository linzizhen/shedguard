"""体表信号指标。

全部是可解释的像素统计，不依赖任何训练权重。
选择 CIELAB 的 L 而不是 RGB 均值，是因为 L 更接近感知亮度，
且与曝光近似线性，归一化后残差更小。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import FloatImage, ImageFrame

BOX_INSET_RATIO = 0.1
HIGH_LIGHT_THRESHOLD = 80.0
CANNY_LOW = 80
CANNY_HIGH = 160
HUE_BINS = 36


@dataclass(frozen=True, slots=True)
class ImageMetrics:
    """一天一帧的体表信号。"""

    lightness_mean: float
    lightness_std: float
    saturation_mean: float
    high_light_ratio: float
    edge_density: float
    color_entropy: float
    background_lightness: float


def _body_box(detection: Detection, frame: ImageFrame) -> tuple[int, int, int, int]:
    """把检测框裁进画面，再向内收缩，避开框边缘混入的背景像素。"""
    x1 = max(0, min(detection.x1, frame.width - 1))
    y1 = max(0, min(detection.y1, frame.height - 1))
    x2 = max(x1 + 1, min(detection.x2, frame.width))
    y2 = max(y1 + 1, min(detection.y2, frame.height))

    inset_x = round((x2 - x1) * BOX_INSET_RATIO)
    inset_y = round((y2 - y1) * BOX_INSET_RATIO)

    inner_x1 = min(x1 + inset_x, x2 - 1)
    inner_y1 = min(y1 + inset_y, y2 - 1)
    inner_x2 = max(x2 - inset_x, inner_x1 + 1)
    inner_y2 = max(y2 - inset_y, inner_y1 + 1)
    return inner_x1, inner_y1, inner_x2, inner_y2


def _srgb_to_linear(rgb: NDArray[np.float32]) -> NDArray[np.float32]:
    """sRGB 编码值（0–1）转线性光。"""
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4).astype(
        np.float32
    )


def _linear_to_srgb(linear: NDArray[np.float32]) -> NDArray[np.float32]:
    """线性光（0–1）转 sRGB 编码值。"""
    encoded = np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(np.maximum(linear, 0.0), 1 / 2.4) - 0.055,
    )
    return cast(FloatImage, encoded.astype(np.float32))


def _lab_lightness(rgb: NDArray[np.float32]) -> NDArray[np.float32]:
    """CIE 1976 L*，取值 0–100。"""
    linear = _srgb_to_linear(rgb)
    luminance = (
        linear[..., 0] * 0.2126 + linear[..., 1] * 0.7152 + linear[..., 2] * 0.0722
    ).astype(np.float32)
    delta = 6.0 / 29.0
    threshold = delta**3
    warped = np.where(
        luminance > threshold,
        np.cbrt(np.maximum(luminance, 0.0)),
        luminance / (3.0 * delta * delta) + 4.0 / 29.0,
    )
    return cast(
        FloatImage, np.clip(116.0 * warped - 16.0, 0.0, 100.0).astype(np.float32)
    )


def lstar_to_luminance(lstar: float) -> float:
    """把 CIE L* 反算成相对亮度 Y（0–1）。

    曝光漂移是乘性的，只在**线性光**空间里比值才有意义；
    L* 经过三次方根变换，直接比 L* 会低估亮部变化。
    """
    if lstar <= 8.0:
        return max(lstar / 903.3, 0.0)
    return float(((lstar + 16.0) / 116.0) ** 3)


def _hue_entropy(hue: NDArray[np.uint8]) -> float:
    bins = (hue.astype(np.int32) * HUE_BINS // 180).ravel()
    counts = np.bincount(bins, minlength=HUE_BINS).astype(np.float64)
    total = counts.sum()
    if total <= 0:
        return 0.0
    probabilities = counts[counts > 0] / total
    return float(-np.sum(probabilities * np.log(probabilities)))


def compute_metrics(
    frame: ImageFrame,
    detection: Detection,
    *,
    exposure_scale: float = 1.0,
) -> ImageMetrics:
    """计算一帧的体表信号。

    `exposure_scale` 是当天的曝光系数：画面比基线亮多少倍，就除以多少，
    把「灯光变亮」与「体表变白」分开。除法在**线性光**空间做，
    否则 sRGB 的伽马会把校正量放大。
    """
    rgb = frame.rgb.astype(np.float32) / 255.0
    if exposure_scale > 0 and exposure_scale != 1.0:
        linear = _srgb_to_linear(rgb)
        linear = np.clip(linear / exposure_scale, 0.0, 1.0)
        rgb = _linear_to_srgb(linear)
    lightness = _lab_lightness(rgb)

    x1, y1, x2, y2 = _body_box(detection, frame)
    body_lightness = lightness[y1:y2, x1:x2]
    body_rgb = np.clip(rgb[y1:y2, x1:x2] * 255.0, 0.0, 255.0).astype(np.uint8)

    hsv = cv2.cvtColor(body_rgb, cv2.COLOR_RGB2HSV)
    gray = (np.clip(body_lightness, 0.0, 100.0) * 2.55).astype(np.uint8)
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)

    mask = np.ones(lightness.shape, dtype=bool)
    mask[y1:y2, x1:x2] = False
    background = lightness[mask] if bool(mask.any()) else lightness.ravel()

    return ImageMetrics(
        lightness_mean=float(body_lightness.mean()),
        lightness_std=float(body_lightness.std()),
        saturation_mean=float(hsv[..., 1].astype(np.float32).mean() / 255.0),
        high_light_ratio=float((body_lightness >= HIGH_LIGHT_THRESHOLD).mean()),
        edge_density=float((edges > 0).mean()),
        color_entropy=_hue_entropy(hsv[..., 0]),
        background_lightness=float(np.median(background)),
    )
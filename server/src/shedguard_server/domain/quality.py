"""输入质量门：判断一张图够不够看清，不够就别让分类器发言。

背景见 `docs/specs/2026-11-25-input-quality-gate-design.md`。

设计要点：

1. 指标全部在**检测框裁剪图缩放到 224×224 之后**计算 —— 与分类器的实际输入
   完全一致，数值不随原图分辨率漂移。标定时的实测也是这么量的。
2. 只做「能不能看清」的判断，不猜状态。看不清就回 `unknown` + 原因。
3. 顺序固定：太糊 → 太暗 → 过曝。一张图同时满足多条时，按这个优先级报一条，
   避免给用户一次抛四个问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.metrics import _lab_lightness

#: 指标计算分辨率。必须与状态分类器的输入边长一致（`DEFAULT_INPUT_SIZE`），
#: 否则标定出来的阈值不可迁移。
MEASURE_SIZE: Final = 224

#: 通道值达到这个数就算削顶（数据已经丢了，不是浅色）。
SATURATED_LEVEL: Final = 250

#: 默认阈值，来源是 349 张验证图 × 9 档退化的实测标定（规格 §5）。
DEFAULT_MIN_SHARPNESS: Final = 25.0
DEFAULT_MIN_LIGHTNESS: Final = 18.0
DEFAULT_MAX_SATURATED: Final = 0.20


class QualityReason(StrEnum):
    """看不清的具体原因。值会落库、会进接口响应，改动需同步迁移与 App。"""

    TOO_BLURRY = "too_blurry"
    TOO_DARK = "too_dark"
    OVEREXPOSED = "overexposed"
    NO_SUBJECT = "no_subject"


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """一张裁剪图的质量指标，保留原始数值便于排查与重新标定。"""

    sharpness: float
    lightness: float
    saturated: float


@dataclass(frozen=True, slots=True)
class QualityVerdict:
    """质量判定结果。

    `reason` 为 None 表示通过；不通过时 `metrics` 仍然保留，
    这样接口和日志能说清「到底是哪一项不达标、差多少」。
    """

    reason: QualityReason | None
    metrics: QualityMetrics | None


def measure_quality(frame: ImageFrame, *, measure_size: int = MEASURE_SIZE) -> QualityMetrics:
    """量一张**已裁剪**的图的质量指标。

    缩放用 `INTER_LINEAR`、灰度用 `COLOR_RGB2GRAY`，与标定脚本逐字一致 ——
    换插值方式会让拉普拉斯方差整体漂移，阈值就得重标。
    """
    if frame.width != measure_size or frame.height != measure_size:
        # cv2.resize 返回的类型在 numpy 的 stub 里被放宽成整数/浮点联合，
        # 这里明确断言回 uint8（INTER_LINEAR 对 uint8 输入不会改变 dtype）。
        resized: NDArray[np.uint8] = cast(
            NDArray[np.uint8],
            cv2.resize(frame.rgb, (measure_size, measure_size), interpolation=cv2.INTER_LINEAR),
        )
    else:
        resized = frame.rgb

    gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    lightness = float(_lab_lightness(resized.astype(np.float32) / 255.0).mean())
    saturated = float((resized.max(axis=2) >= SATURATED_LEVEL).mean())
    return QualityMetrics(sharpness=sharpness, lightness=lightness, saturated=saturated)


def evaluate_quality(
    frame: ImageFrame,
    *,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    min_lightness: float = DEFAULT_MIN_LIGHTNESS,
    max_saturated: float = DEFAULT_MAX_SATURATED,
    measure_size: int = MEASURE_SIZE,
) -> QualityVerdict:
    """判断裁剪图是否够清晰。

    三条门按「太糊 → 太暗 → 过曝」的顺序判定，命中即返回，只报第一条。
    阈值全部由调用方传入，这里不读配置 —— 保持纯函数，便于单测与标定脚本对齐。
    """
    metrics = measure_quality(frame, measure_size=measure_size)
    if metrics.sharpness < min_sharpness:
        return QualityVerdict(reason=QualityReason.TOO_BLURRY, metrics=metrics)
    if metrics.lightness < min_lightness:
        return QualityVerdict(reason=QualityReason.TOO_DARK, metrics=metrics)
    if metrics.saturated > max_saturated:
        return QualityVerdict(reason=QualityReason.OVEREXPOSED, metrics=metrics)
    return QualityVerdict(reason=None, metrics=metrics)

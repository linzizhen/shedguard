"""图像帧的内存表示。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Uint8Image = NDArray[np.uint8]
FloatImage = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class ImageFrame:
    """一张已解码的 RGB 图像。

    约定 `rgb` 的形状为 `(height, width, 3)`，通道顺序为 RGB。
    解码层负责把 OpenCV 默认的 BGR 转成 RGB。
    """

    width: int
    height: int
    rgb: Uint8Image

    def __post_init__(self) -> None:
        expected = (self.height, self.width, 3)
        if self.rgb.shape != expected:
            raise ValueError(f"像素数组形状 {self.rgb.shape} 与尺寸 {expected} 不一致")
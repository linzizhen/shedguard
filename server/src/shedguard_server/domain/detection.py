"""守宫定位的抽象与零依赖实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shedguard_server.domain.imaging import ImageFrame


@dataclass(frozen=True, slots=True)
class Detection:
    """一个检测框，坐标为像素，左上原点。"""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    def __post_init__(self) -> None:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(f"检测框无效: ({self.x1}, {self.y1}) -> ({self.x2}, {self.y2})")

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2

    @property
    def area(self) -> int:
        return (self.x2 - self.x1) * (self.y2 - self.y1)


class Detector(Protocol):
    """把一张图缩到一个守宫所在的框。"""

    @property
    def name(self) -> str:
        """写进指标记录的检测器标识，用于事后追溯。"""
        ...

    def detect(self, frame: ImageFrame) -> Detection | None:
        """返回检测框；画面里找不到守宫时返回 None。"""
        ...


@dataclass(frozen=True, slots=True)
class NullDetector:
    """把整幅图当作守宫区域。

    没有权重文件时用它保证链路可跑，也让测试不依赖模型。
    """

    name: str = "null-detector"

    def detect(self, frame: ImageFrame) -> Detection | None:
        return Detection(x1=0, y1=0, x2=frame.width, y2=frame.height, confidence=1.0)
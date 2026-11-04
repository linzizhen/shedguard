"""蜕皮状态识别：单帧状态、每日聚合与事件推导。

「已蜕完」不是视觉状态 —— 皮掉完之后守宫恢复常态，与从未蜕皮在单帧上
不可区分。它只能由「蜕皮中 → 正常」的转换推导出来。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from shedguard_server.domain.imaging import ImageFrame

#: 概率分布求和的容差。ONNX 输出经 float32 往返，不必要求严格等于 1。
PROBABILITY_TOLERANCE: Final = 1e-3

#: 一次查询允许的最大跨度，与判定层保持一致。
MAX_STATE_DAYS: Final = 366

EVENT_STARTED: Final = "shed_started"
EVENT_COMPLETED: Final = "shed_completed"


class ShedState(StrEnum):
    """一张图或一天所处的蜕皮状态。

    ``UNKNOWN`` 不是模型类别，而是服务层的判定：没找到守宫，或分类置信度不足。
    """

    NORMAL = "normal"
    OPAQUE = "opaque"
    SHEDDING = "shedding"
    UNKNOWN = "unknown"


#: 平票时的取用顺序：越接近蜕皮越优先。
#: 漏报一次蜕皮的代价（卡皮、趾头坏死）高于让用户多看一眼。
VOTE_PRIORITY: Final[tuple[ShedState, ...]] = (
    ShedState.SHEDDING,
    ShedState.OPAQUE,
    ShedState.NORMAL,
)

#: 视为「正在蜕皮过程中」的状态。
SHEDDING_STATES: Final[frozenset[ShedState]] = frozenset(
    {ShedState.OPAQUE, ShedState.SHEDDING}
)


@dataclass(frozen=True, slots=True)
class StatePrediction:
    """分类器对一张已裁剪守宫图的输出。"""

    state: ShedState
    confidence: float
    probabilities: Mapping[str, float]

    def __post_init__(self) -> None:
        if self.state is ShedState.UNKNOWN:
            raise ValueError("分类器不能直接输出 unknown，那是服务层的判定")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"置信度必须在 0 与 1 之间: {self.confidence}")
        if not self.probabilities:
            raise ValueError("概率分布不能为空")
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > PROBABILITY_TOLERANCE:
            raise ValueError(f"概率之和应为 1，实际为 {total:.6f}")


class StateClassifier(Protocol):
    """把一张已裁剪的守宫图判成某个蜕皮状态。"""

    @property
    def name(self) -> str:
        """写进状态记录的分类器标识，用于事后追溯。"""
        ...

    def classify(self, frame: ImageFrame) -> StatePrediction:
        """返回三态之一；置信度不足由调用方降级为 unknown。"""
        ...


@dataclass(frozen=True, slots=True)
class DailyState:
    """一天聚合后的状态；``state`` 为 None 表示当天没有任何有效观测。"""

    local_date: date
    state: ShedState | None
    votes: Mapping[str, int]
    image_count: int


@dataclass(frozen=True, slots=True)
class ShedEventDetected:
    """由状态转换推导出的蜕皮事件。"""

    event_type: str
    local_date: date
    previous: ShedState
    current: ShedState


def crop_box(
    box: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    padding: float,
) -> tuple[int, int, int, int]:
    """按比例外扩检测框，并夹紧到画面内。

    外扩是为了把贴着框边的皮屑也带进来 —— 蜕皮时皮往往从身体边缘翘起。
    """
    x1, y1, x2, y2 = box
    pad_x = round((x2 - x1) * padding)
    pad_y = round((y2 - y1) * padding)
    return (
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(width, x2 + pad_x),
        min(height, y2 + pad_y),
    )


def crop_frame(frame: ImageFrame, box: tuple[int, int, int, int]) -> ImageFrame:
    """从原图裁出一块区域，返回新的 `ImageFrame`。"""
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"裁剪区域无效: ({x1}, {y1}) -> ({x2}, {y2})")
    region = np.ascontiguousarray(frame.rgb[y1:y2, x1:x2])
    return ImageFrame(width=int(region.shape[1]), height=int(region.shape[0]), rgb=region)


def aggregate(states: Sequence[ShedState]) -> ShedState | None:
    """把一天的多次观测聚成一个状态。

    ``unknown`` 不参与投票 —— 它表示「没看见」，不是「看见了正常」。
    全部为 unknown 时返回 None，即这一天没有状态。
    """
    counted = [state for state in states if state is not ShedState.UNKNOWN]
    if not counted:
        return None

    tally = Counter(counted)
    top = max(tally.values())
    tied = {state for state, count in tally.items() if count == top}
    return next(state for state in VOTE_PRIORITY if state in tied)


def derive_events(days: Sequence[DailyState]) -> list[ShedEventDetected]:
    """从每日状态序列推导蜕皮开始与完成。

    没有状态的日子被跳过而不是打断序列 —— 缺一天图不代表蜕皮结束了。
    """
    events: list[ShedEventDetected] = []
    previous: ShedState | None = None

    for day in days:
        current = day.state
        if current is None:
            continue

        if previous is not None and current is not previous:
            if previous is ShedState.NORMAL and current in SHEDDING_STATES:
                events.append(
                    ShedEventDetected(EVENT_STARTED, day.local_date, previous, current)
                )
            elif previous in SHEDDING_STATES and current is ShedState.NORMAL:
                events.append(
                    ShedEventDetected(EVENT_COMPLETED, day.local_date, previous, current)
                )

        previous = current

    return events


def softmax(logits: NDArray[np.float32]) -> NDArray[np.float32]:
    """数值稳定的 softmax；导出模型输出的是 logits，不是概率。"""
    shifted = logits - np.max(logits)
    exponentiated = np.exp(shifted)
    total = float(np.sum(exponentiated))
    return (exponentiated / total).astype(np.float32)

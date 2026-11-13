"""萌照（近景选片）的纯函数层。

原则：这一层不碰数据库、不碰文件系统，只做「哪些图够格、哪张最好、裁成什么样」，
这样选片规则可以被单元测试穷举，也方便以后换成偏好打分模型（P26）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from shedguard_server.domain.imaging import ImageFrame

DEFAULT_MIN_SUBJECT_RATIO: Final = 0.10
DEFAULT_MIN_CONFIDENCE: Final = 0.45
DEFAULT_MAX_HIGHLIGHT: Final = 0.35
DEFAULT_CROP_MARGIN: Final = 1.35
SUBJECT_RATIO_TARGET: Final = 0.35
WEIGHT_SUBJECT: Final = 0.45
WEIGHT_SHARPNESS: Final = 0.35
WEIGHT_CENTER: Final = 0.20
SHARPNESS_FLOOR_RATIO: Final = 0.8
DHASH_SIZE: Final = 8
DHASH_MAX_DISTANCE: Final = 6
DEFAULT_PER_DAY: Final = 1
DEFAULT_START_HOUR: Final = 8
DEFAULT_END_HOUR: Final = 20
MAX_PER_DAY: Final = 6
FEEDBACK_LIKE: Final = "like"
FEEDBACK_SKIP: Final = "skip"
FEEDBACK_CROP_HEAD: Final = "crop_head"
FEEDBACK_KINDS: Final = frozenset({FEEDBACK_LIKE, FEEDBACK_SKIP, FEEDBACK_CROP_HEAD})
ALERT_KIND_PORTRAIT: Final = "portrait_ready"

Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Candidate:
    """一张待选的图：检测结果 + 体表指标 + 原图尺寸。"""

    image_id: str
    box: Box | None
    detector_confidence: float | None
    edge_density: float | None
    high_light_ratio: float | None
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: Candidate
    subject_ratio: float
    sharpness: float
    center_score: float
    score: float


def box_area(box: Box) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def subject_ratio(box: Box, width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    return box_area(box) / float(width * height)


def center_score(box: Box, width: int, height: int) -> float:
    """框中心离画面中心越近越接近 1；贴边时为 0。"""
    if width <= 0 or height <= 0:
        return 0.0
    x1, y1, x2, y2 = box
    dx = (x1 + x2) / 2.0 - width / 2.0
    dy = (y1 + y2) / 2.0 - height / 2.0
    farthest = math.hypot(width / 2.0, height / 2.0)
    if farthest <= 0:
        return 0.0
    return max(0.0, 1.0 - math.hypot(dx, dy) / farthest)


def passes_thresholds(
    candidate: Candidate,
    *,
    min_subject_ratio: float = DEFAULT_MIN_SUBJECT_RATIO,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_highlight: float = DEFAULT_MAX_HIGHLIGHT,
) -> bool:
    if candidate.box is None:
        return False
    if candidate.detector_confidence is None or candidate.detector_confidence < min_confidence:
        return False
    if subject_ratio(candidate.box, candidate.width, candidate.height) < min_subject_ratio:
        return False
    return not (
        candidate.high_light_ratio is not None and candidate.high_light_ratio > max_highlight
    )


def rank_candidates(
    candidates: list[Candidate],
    *,
    min_subject_ratio: float = DEFAULT_MIN_SUBJECT_RATIO,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_highlight: float = DEFAULT_MAX_HIGHLIGHT,
    sharpness_floor_ratio: float = SHARPNESS_FLOOR_RATIO,
) -> list[ScoredCandidate]:
    """过滤 + 打分 + 排序（分数从高到低）。

    清晰度是**当天内部相对比较**：先过一遍硬门槛，再用剩余候选的清晰度中位数乘
    一个系数当下限。这样阴天整体偏糊时不会一张都选不出来，也不会把糊图选成最佳。
    """
    eligible = [
        candidate
        for candidate in candidates
        if passes_thresholds(
            candidate,
            min_subject_ratio=min_subject_ratio,
            min_confidence=min_confidence,
            max_highlight=max_highlight,
        )
    ]
    if not eligible:
        return []

    sharpness_values = sorted(
        float(candidate.edge_density)
        for candidate in eligible
        if candidate.edge_density is not None
    )
    if sharpness_values:
        median = sharpness_values[len(sharpness_values) // 2]
        floor = median * sharpness_floor_ratio
        eligible = [
            candidate
            for candidate in eligible
            if candidate.edge_density is not None
            and float(candidate.edge_density) >= floor
        ]
    if not eligible:
        return []

    best_sharpness = max(
        (
            float(candidate.edge_density)
            for candidate in eligible
            if candidate.edge_density is not None
        ),
        default=0.0,
    )

    scored: list[ScoredCandidate] = []
    for candidate in eligible:
        assert candidate.box is not None  # 已由 passes_thresholds 保证
        ratio = subject_ratio(candidate.box, candidate.width, candidate.height)
        sharpness = float(candidate.edge_density or 0.0)
        centered = center_score(candidate.box, candidate.width, candidate.height)
        sharpness_score = min(sharpness / best_sharpness, 1.0) if best_sharpness > 0 else 0.0
        score = (
            WEIGHT_SUBJECT * min(ratio / SUBJECT_RATIO_TARGET, 1.0)
            + WEIGHT_SHARPNESS * sharpness_score
            + WEIGHT_CENTER * centered
        )
        scored.append(
            ScoredCandidate(
                candidate=candidate,
                subject_ratio=ratio,
                sharpness=sharpness,
                center_score=centered,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def square_crop_box(
    box: Box,
    width: int,
    height: int,
    *,
    margin: float = DEFAULT_CROP_MARGIN,
) -> Box:
    """以检测框为中心裁一个正方形（外扩 margin 倍），并夹紧在画面内。"""
    x1, y1, x2, y2 = box
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    side = round(max(x2 - x1, y2 - y1) * margin)
    side = max(1, min(side, width, height))
    left = round(center_x - side / 2.0)
    top = round(center_y - side / 2.0)
    left = max(0, min(left, width - side))
    top = max(0, min(top, height - side))
    return (left, top, left + side, top + side)


def crop_square(frame: ImageFrame, box: Box) -> ImageFrame:
    x1, y1, x2, y2 = box
    region = frame.rgb[y1:y2, x1:x2]
    if region.size == 0:
        msg = f"方形裁剪区域无效: {box}"
        raise ValueError(msg)
    return ImageFrame(width=int(region.shape[1]), height=int(region.shape[0]), rgb=region.copy())


def difference_hash(frame: ImageFrame) -> str:
    """8×8 差分哈希，用于「今天别发和昨天一样姿势」的去重。"""
    gray = (
        0.299 * frame.rgb[:, :, 0] + 0.587 * frame.rgb[:, :, 1] + 0.114 * frame.rgb[:, :, 2]
    ).astype("float32")
    ys = max(1, gray.shape[0] // DHASH_SIZE)
    xs = max(1, gray.shape[1] // DHASH_SIZE)
    small = gray[: ys * DHASH_SIZE, : xs * DHASH_SIZE]
    small = small.reshape(DHASH_SIZE, ys, DHASH_SIZE, xs).mean(axis=(1, 3))
    bits = 0
    for row in range(DHASH_SIZE):
        for column in range(DHASH_SIZE - 1):
            bits = (bits << 1) | int(small[row, column] > small[row, column + 1])
    return f"{bits:016x}"


def hash_distance(left: str, right: str) -> int:
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def is_near_duplicate(left: str, right: str, *, threshold: int = DHASH_MAX_DISTANCE) -> bool:
    return hash_distance(left, right) <= threshold


def portrait_rel_path(local_date: date, device_id: str, shot_id: str) -> str:
    return f"portraits/{local_date.isoformat()}/{device_id}/{shot_id}.jpg"


def encode_square(frame: ImageFrame, *, output_px: int, quality: int) -> bytes:
    """把方形帧缩放并编码成 JPEG。"""
    import cv2

    size = max(1, min(output_px, frame.width, frame.height))
    resized = cv2.resize(frame.rgb, (size, size), interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
    ok, buffer = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        msg = "萌照编码失败"
        raise ValueError(msg)
    return buffer.tobytes()


@dataclass(frozen=True, slots=True)
class PortraitShot:
    """一张已生成并落盘的萌照。"""

    id: str
    device_id: str
    pet_id: str | None
    local_date: date
    slot: int
    source_image_id: str | None
    rel_path: str
    width: int
    height: int
    score: float
    created_at_utc: datetime


@dataclass(frozen=True, slots=True)
class PortraitFeedback:
    """用户对一张萌照的反馈：喜欢 / 换一张 / 手动框头。"""

    id: str
    shot_id: str
    owner_id: str | None
    kind: str
    crop_box: Box | None
    created_at_utc: datetime

    def __post_init__(self) -> None:
        if self.kind not in FEEDBACK_KINDS:
            msg = f"未知的反馈类型: {self.kind}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PortraitSetting:
    """一只宠物的萌照偏好；`per_day=0` 等价于关闭。"""

    pet_id: str
    enabled: bool
    per_day: int
    start_hour: int
    end_hour: int
    updated_at_utc: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.per_day <= MAX_PER_DAY:
            msg = f"每天张数必须在 0 到 {MAX_PER_DAY} 之间"
            raise ValueError(msg)
        if not 0 <= self.start_hour <= 23 or not 1 <= self.end_hour <= 24:
            msg = "起止小时超出范围"
            raise ValueError(msg)
        if self.start_hour >= self.end_hour:
            msg = "起始小时必须早于结束小时"
            raise ValueError(msg)
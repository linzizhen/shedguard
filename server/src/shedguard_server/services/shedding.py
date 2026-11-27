"""蜕皮状态识别：单图编排与序列聚合。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

from shedguard_server.domain.detection import Detection, Detector
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.judgement import validate_range
from shedguard_server.domain.models import ImageRecord, SheddingState
from shedguard_server.domain.quality import (
    DEFAULT_MAX_SATURATED,
    DEFAULT_MIN_LIGHTNESS,
    DEFAULT_MIN_SHARPNESS,
    MEASURE_SIZE,
    QualityReason,
    evaluate_quality,
)
from shedguard_server.domain.shedding import (
    DailyState,
    ShedEventDetected,
    ShedState,
    StateClassifier,
    StatePrediction,
    aggregate,
    crop_box,
    crop_frame,
    derive_events,
)
from shedguard_server.domain.validation import validate_device_id
from shedguard_server.errors import (
    InvalidRequestError,
    ModelUnavailableError,
    NotFoundError,
)
from shedguard_server.infra.imaging import decode_image
from shedguard_server.infra.repository import ImageRepository, SheddingStateRepository
from shedguard_server.infra.storage import LocalStorage

#: 状态定义版本。改变判定规则时递增，旧记录会被重算。
#: v2：新增输入质量门（看不清的图记 unknown + quality_reason）。
STATE_VERSION: Final = "2"

#: 每日投票固定输出这三个键，即使某类当天为零。
VOTE_KEYS: Final[tuple[ShedState, ...]] = (
    ShedState.NORMAL,
    ShedState.OPAQUE,
    ShedState.SHEDDING,
)


@dataclass(frozen=True, slots=True)
class SheddingReport:
    """一段区间内的每日状态与推导出的蜕皮事件。"""

    device_id: str
    start: date
    end: date
    days: list[DailyState]
    events: list[ShedEventDetected]
    current_state: ShedState | None


class SheddingService:
    """定位 → 裁剪 → 分类 → 落库，以及按日聚合与事件推导。"""

    def __init__(
        self,
        images: ImageRepository,
        states: SheddingStateRepository,
        storage: LocalStorage,
        detector: Detector,
        classifier: StateClassifier | None,
        *,
        min_confidence: float = 0.6,
        crop_padding: float = 0.08,
        quality_gate: bool = False,
        quality_min_sharpness: float = DEFAULT_MIN_SHARPNESS,
        quality_min_lightness: float = DEFAULT_MIN_LIGHTNESS,
        quality_max_saturated: float = DEFAULT_MAX_SATURATED,
        quality_measure_size: int = MEASURE_SIZE,
    ) -> None:
        self._images = images
        self._states = states
        self._storage = storage
        self._detector = detector
        self._classifier = classifier
        self._min_confidence = min_confidence
        self._crop_padding = crop_padding
        self._quality_gate = quality_gate
        self._quality_min_sharpness = quality_min_sharpness
        self._quality_min_lightness = quality_min_lightness
        self._quality_max_saturated = quality_max_saturated
        self._quality_measure_size = quality_measure_size
        self._pipeline_signature = self._build_signature()

    def _build_signature(self) -> str:
        """把「影响判定结果的参数」压成一个短指纹，用于缓存失效。

        只要这里的任何一项改了，旧结论就不能再用 —— 否则关掉质量门之后，
        同一张照片还会从缓存里拿到「这张有点糊」。
        """
        gate = "on" if self._quality_gate else "off"
        return (
            f"v{STATE_VERSION}|gate={gate}|s={self._quality_min_sharpness:g}"
            f"|l={self._quality_min_lightness:g}|t={self._quality_max_saturated:g}"
            f"|n={self._quality_measure_size}"
            f"|c={self._min_confidence:g}|p={self._crop_padding:g}"
        )

    def analyze(self, image_id: str, *, now: datetime | None = None) -> SheddingState:
        record = self._images.find_by_id(image_id)
        if record is None:
            raise NotFoundError(f"图片不存在: {image_id}")

        classifier = self._classifier
        if classifier is None:
            raise ModelUnavailableError("未配置蜕皮状态分类模型")

        existing = self._states.find(image_id)
        if (
            existing is not None
            and existing.state_version == STATE_VERSION
            and existing.classifier_name == classifier.name
            and existing.pipeline_signature == self._pipeline_signature
        ):
            return existing

        frame = decode_image(self._storage.read(record.rel_path))
        detection = self._detector.detect(frame)
        computed_at = now or datetime.now(UTC)

        if detection is None:
            # 画面里没有守宫：记 unknown 而不是猜一个 normal。
            state = self._build(
                record,
                state=ShedState.UNKNOWN,
                confidence=None,
                probabilities=None,
                box=None,
                computed_at=computed_at,
                classifier_name=classifier.name,
                quality_reason=(
                    QualityReason.NO_SUBJECT.value if self._quality_gate else None
                ),
            )
        else:
            box = crop_box(
                detection.box,
                width=frame.width,
                height=frame.height,
                padding=self._crop_padding,
            )
            crop = crop_frame(frame, box)
            reason = self._check_quality(crop)
            if reason is not None:
                # 看不清就不让分类器发言：记 unknown 并说明原因，
                # 避免模型对一张糊图给出一个高置信度的错误结论。
                state = self._build(
                    record,
                    state=ShedState.UNKNOWN,
                    confidence=None,
                    probabilities=None,
                    box=box,
                    computed_at=computed_at,
                    classifier_name=classifier.name,
                    quality_reason=reason.value,
                )
            else:
                prediction = classifier.classify(crop)
                state = self._from_prediction(
                    record, detection, prediction, box, computed_at, classifier.name
                )

        self._states.save(state)
        return state

    def _check_quality(self, crop: ImageFrame) -> QualityReason | None:
        """质量门关闭时恒返回 None，不产生任何额外计算。"""
        if not self._quality_gate:
            return None
        verdict = evaluate_quality(
            crop,
            min_sharpness=self._quality_min_sharpness,
            min_lightness=self._quality_min_lightness,
            max_saturated=self._quality_max_saturated,
            measure_size=self._quality_measure_size,
        )
        return verdict.reason

    def series(self, *, device_id_raw: str, start: date, end: date) -> SheddingReport:
        device_id = validate_device_id(device_id_raw)
        try:
            validate_range(start, end)
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc

        records = self._states.list_for_device(device_id, start, end)
        observed: dict[date, list[ShedState]] = {}
        for record in records:
            observed.setdefault(record.local_date, []).append(ShedState(record.state))

        days: list[DailyState] = []
        cursor = start
        while cursor <= end:
            states = observed.get(cursor, [])
            tally = Counter(states)
            days.append(
                DailyState(
                    local_date=cursor,
                    state=aggregate(states),
                    votes={key.value: tally.get(key, 0) for key in VOTE_KEYS},
                    image_count=len(states),
                )
            )
            cursor += timedelta(days=1)

        events = derive_events(days)
        current = next(
            (day.state for day in reversed(days) if day.state is not None), None
        )
        return SheddingReport(
            device_id=device_id,
            start=start,
            end=end,
            days=days,
            events=events,
            current_state=current,
        )

    def _from_prediction(
        self,
        record: ImageRecord,
        detection: Detection,
        prediction: StatePrediction,
        box: tuple[int, int, int, int],
        computed_at: datetime,
        classifier_name: str,
    ) -> SheddingState:
        """置信度不足时降级为 unknown，但保留完整概率分布供排查。"""
        state = (
            prediction.state
            if prediction.confidence >= self._min_confidence
            else ShedState.UNKNOWN
        )
        return self._build(
            record,
            state=state,
            confidence=prediction.confidence if state is not ShedState.UNKNOWN else None,
            probabilities=dict(prediction.probabilities),
            box=box,
            computed_at=computed_at,
            classifier_name=classifier_name,
        )

    def _build(
        self,
        record: ImageRecord,
        *,
        state: ShedState,
        confidence: float | None,
        probabilities: dict[str, float] | None,
        box: tuple[int, int, int, int] | None,
        computed_at: datetime,
        classifier_name: str,
        quality_reason: str | None = None,
    ) -> SheddingState:
        return SheddingState(
            image_id=record.id,
            device_id=record.device_id,
            local_date=record.local_date,
            state=state.value,
            confidence=confidence,
            probabilities=probabilities,
            detector_name=self._detector.name,
            classifier_name=classifier_name,
            box=box,
            computed_at_utc=computed_at,
            state_version=STATE_VERSION,
            quality_reason=quality_reason,
            pipeline_signature=self._pipeline_signature,
        )

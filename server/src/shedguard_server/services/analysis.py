"""把一张图跑成一组体表指标。"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Final

from shedguard_server.domain.detection import Detection, Detector
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.metrics import compute_metrics
from shedguard_server.domain.models import FrameMetric, ImageRecord
from shedguard_server.errors import NotFoundError
from shedguard_server.infra.imaging import decode_image
from shedguard_server.infra.repository import FrameMetricRepository, ImageRepository
from shedguard_server.infra.storage import LocalStorage

METRICS_VERSION: Final = "1"
MIN_EXPOSURE_SCALE: Final = 0.5
MAX_EXPOSURE_SCALE: Final = 2.0


class AnalysisService:
    """定位 + 光照归一化 + 指标提取。

    一次分析分两遍算：第一遍取 `background_lightness` 估算曝光系数，
    第二遍带着系数重算。多花一次计算，换来「灯光变亮」与「体表变白」的分离。
    """

    def __init__(
        self,
        images: ImageRepository,
        metrics: FrameMetricRepository,
        storage: LocalStorage,
        detector: Detector,
        *,
        background_days: int = 7,
    ) -> None:
        self._images = images
        self._metrics = metrics
        self._storage = storage
        self._detector = detector
        self._background_days = background_days

    @property
    def metrics_version(self) -> str:
        return METRICS_VERSION

    def analyze(self, image_id: str, *, now: datetime | None = None) -> FrameMetric:
        record = self._images.find_by_id(image_id)
        if record is None:
            raise NotFoundError(f"图片不存在: {image_id}")

        existing = self._metrics.find(image_id)
        if (
            existing is not None
            and existing.metrics_version == METRICS_VERSION
            and existing.detector_name == self._detector.name
        ):
            return existing

        frame = decode_image(self._storage.read(record.rel_path))
        detection = self._detector.detect(frame)
        exposure_scale, normalized = self._exposure_scale(record, frame, detection)

        computed_at = now or datetime.now(UTC)
        if detection is None:
            metric = self._empty_metric(record, computed_at, exposure_scale, normalized)
        else:
            values = compute_metrics(frame, detection, exposure_scale=exposure_scale)
            metric = FrameMetric(
                image_id=record.id,
                device_id=record.device_id,
                local_date=record.local_date,
                detected=True,
                box=detection.box,
                detector_name=self._detector.name,
                detector_confidence=detection.confidence,
                normalized=normalized,
                exposure_scale=exposure_scale,
                lightness_mean=values.lightness_mean,
                lightness_std=values.lightness_std,
                saturation_mean=values.saturation_mean,
                high_light_ratio=values.high_light_ratio,
                edge_density=values.edge_density,
                color_entropy=values.color_entropy,
                background_lightness=values.background_lightness,
                computed_at_utc=computed_at,
                metrics_version=METRICS_VERSION,
            )

        self._metrics.save(metric)
        return metric

    def _exposure_scale(
        self, record: ImageRecord, frame: ImageFrame, detection: Detection | None
    ) -> tuple[float, bool]:
        if detection is None:
            return 1.0, False

        probe = compute_metrics(frame, detection, exposure_scale=1.0)
        history = self._metrics.recent_background(
            record.device_id, before=record.local_date, days=self._background_days
        )
        if not history or probe.background_lightness <= 0:
            return 1.0, False

        reference = statistics.median(history)
        scale = reference / probe.background_lightness
        if scale <= 0:
            return 1.0, False
        return min(max(scale, MIN_EXPOSURE_SCALE), MAX_EXPOSURE_SCALE), True

    def _empty_metric(
        self,
        record: ImageRecord,
        computed_at: datetime,
        exposure_scale: float,
        normalized: bool,
    ) -> FrameMetric:
        return FrameMetric(
            image_id=record.id,
            device_id=record.device_id,
            local_date=record.local_date,
            detected=False,
            box=None,
            detector_name=self._detector.name,
            detector_confidence=None,
            normalized=normalized,
            exposure_scale=exposure_scale,
            lightness_mean=None,
            lightness_std=None,
            saturation_mean=None,
            high_light_ratio=None,
            edge_density=None,
            color_entropy=None,
            background_lightness=None,
            computed_at_utc=computed_at,
            metrics_version=METRICS_VERSION,
        )
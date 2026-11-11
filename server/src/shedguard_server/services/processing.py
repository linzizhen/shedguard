"""上传后的自动处理流水线：算指标 → 判蜕皮状态 → 跃迁则建提醒并推送。

由 `api/routes/images.py` 通过 FastAPI 的 `BackgroundTasks` 触发；运行在独立会话，
任何异常都只记日志，绝不影响上传接口的响应。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.alerts import SHEDDING_STATE
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.push import PushGateway
from shedguard_server.domain.shedding import ShedState, StateClassifier, aggregate
from shedguard_server.infra.repository import (
    AlertRepository,
    FrameMetricRepository,
    ImageRepository,
    PushDeviceRepository,
    SheddingStateRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.alerts import AlertService
from shedguard_server.services.analysis import AnalysisService
from shedguard_server.services.shedding import SheddingService

logger = logging.getLogger("shedguard.pipeline")

#: 往前找「上一个有状态的日子」的回溯窗口。
PREVIOUS_WINDOW_DAYS = 30


def process_image(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    detector: Detector,
    classifier: StateClassifier | None,
    storage: LocalStorage,
    gateway: PushGateway,
    image_id: str,
) -> None:
    """上传后的后台处理入口；永不抛异常。"""
    try:
        with session_factory() as session:
            _run(
                session,
                settings=settings,
                detector=detector,
                classifier=classifier,
                storage=storage,
                gateway=gateway,
                image_id=image_id,
            )
    except Exception:  # 后台任务不能把异常抛回请求
        logger.exception("上传后处理失败 image_id=%s", image_id)


def _run(
    session: Session,
    *,
    settings: Settings,
    detector: Detector,
    classifier: StateClassifier | None,
    storage: LocalStorage,
    gateway: PushGateway,
    image_id: str,
) -> None:
    images = ImageRepository(session)
    record = images.find_by_id(image_id)
    if record is None:
        logger.warning("后处理找不到图片 image_id=%s", image_id)
        return

    metrics = FrameMetricRepository(session)
    states = SheddingStateRepository(session)

    analysis = AnalysisService(
        images, metrics, storage, detector, background_days=settings.background_days
    )
    analysis.analyze(image_id)

    if classifier is None:
        logger.info("未配置状态分类模型，跳过蜕皮判定 image_id=%s", image_id)
        return

    shedding = SheddingService(
        images,
        states,
        storage,
        detector,
        classifier,
        min_confidence=settings.state_min_confidence,
        crop_padding=settings.state_crop_padding,
    )
    state = shedding.analyze(image_id)

    if state.state != SHEDDING_STATE:
        logger.info("状态非蜕皮中 image_id=%s state=%s", image_id, state.state)
        return

    previous = _previous_state(states, record.device_id, state.local_date)
    if previous is ShedState.SHEDDING:
        logger.info("上一有状态日已是蜕皮中，不重复提醒 device=%s", record.device_id)
        return

    devices = PushDeviceRepository(session)
    alert_service = AlertService(
        AlertRepository(session),
        devices,
        gateway,
        cooldown_hours=settings.alert_cooldown_hours,
    )
    alert = alert_service.create_for_transition(
        device_id=state.device_id,
        local_date=state.local_date,
        state=state.state,
        image_id=state.image_id,
        confidence=state.confidence,
        pet_id=devices.pet_for_device(record.device_id),
    )
    if alert is not None:
        delivered = alert_service.deliver(alert)
        logger.info(
            "已创建蜕皮提醒 alert_id=%s push_status=%s", delivered.id, delivered.push_status
        )


def _previous_state(
    states: SheddingStateRepository, device_id: str, today: date
) -> ShedState | None:
    """往前找最近一个「有状态」的日子并聚合；全部未知则返回 None。"""
    end = today - timedelta(days=1)
    start = today - timedelta(days=PREVIOUS_WINDOW_DAYS)
    if end < start:
        return None
    records = states.list_for_device(device_id, start, end)
    by_day: dict[date, list[ShedState]] = {}
    for record in records:
        by_day.setdefault(record.local_date, []).append(ShedState(record.state))
    for day in sorted(by_day, reverse=True):
        aggregated = aggregate(by_day[day])
        if aggregated is not None:
            return aggregated
    return None

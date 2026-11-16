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
from shedguard_server.infra.contribution_upload import ContributionUploader
from shedguard_server.infra.repository import (
    AlertRepository,
    ContributionExportRepository,
    ContributionSampleRepository,
    ContributionSettingRepository,
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    PushDeviceRepository,
    SheddingStateRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.alerts import AlertService
from shedguard_server.services.analysis import AnalysisService
from shedguard_server.services.contributions import ContributionService
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
    contribution_uploader: ContributionUploader,
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
                contribution_uploader=contribution_uploader,
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
    contribution_uploader: ContributionUploader,
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

    devices = PushDeviceRepository(session)
    _enqueue_contribution(
        session,
        settings=settings,
        storage=storage,
        uploader=contribution_uploader,
        device_id=state.device_id,
        source_image_id=state.image_id,
        state=state.state,
        confidence=state.confidence,
        local_date=state.local_date,
    )

    previous = _previous_state(states, record.device_id, state.local_date)
    if previous is ShedState.SHEDDING:
        logger.info("上一有状态日已是蜕皮中，不重复提醒 device=%s", record.device_id)
        return

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


def _enqueue_contribution(
    session: Session,
    *,
    settings: Settings,
    storage: LocalStorage,
    uploader: ContributionUploader,
    device_id: str,
    source_image_id: str,
    state: str,
    confidence: float | None,
    local_date: date,
) -> None:
    """把这张图排进「用户自愿分享」队列；失败只记日志，绝不影响提醒。"""
    devices = PushDeviceRepository(session)
    owner_id = devices.owner_for_device(device_id)
    if owner_id is None:
        return
    try:
        service = ContributionService(
            settings=ContributionSettingRepository(session),
            samples=ContributionSampleRepository(session),
            exports=ContributionExportRepository(session),
            pets=PetRepository(session),
            devices=devices,
            images=ImageRepository(session),
            metrics=FrameMetricRepository(session),
            storage=storage,
            uploader=uploader,
            per_event_limit=settings.contribution_per_event_limit,
            max_pending=settings.contribution_max_pending,
            crop_padding=settings.contribution_crop_padding,
            upload_batch_size=settings.contribution_upload_batch,
        )
        sample = service.enqueue_for_event(
            device_id=device_id,
            owner_id=owner_id,
            pet_id=devices.pet_for_device(device_id),
            source_image_id=source_image_id,
            state=state,
            confidence=confidence,
            local_date=local_date,
        )
    except Exception:  # 分享出问题不能拖垮蜕皮提醒
        logger.exception("入队数据贡献失败 image_id=%s", source_image_id)
        return
    if sample is not None:
        logger.info("已入队数据贡献 sample_id=%s", sample.id)


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

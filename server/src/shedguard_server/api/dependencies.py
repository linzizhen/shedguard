"""HTTP 层共享依赖：配置、数据库会话、仓储、存储与检测器。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector
from shedguard_server.domain.shedding import StateClassifier
from shedguard_server.infra.repository import (
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    SheddingStateRepository,
    ShedRecordRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.judgement import JudgementService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_image_repository(session: Annotated[Session, Depends(get_session)]) -> ImageRepository:
    return ImageRepository(session)


def get_metric_repository(
    session: Annotated[Session, Depends(get_session)],
) -> FrameMetricRepository:
    return FrameMetricRepository(session)


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> LocalStorage:
    return LocalStorage(settings.data_dir)


def get_shedding_state_repository(
    session: Annotated[Session, Depends(get_session)],
) -> SheddingStateRepository:
    return SheddingStateRepository(session)


def get_pet_repository(
    session: Annotated[Session, Depends(get_session)],
) -> PetRepository:
    return PetRepository(session)


def get_shed_record_repository(
    session: Annotated[Session, Depends(get_session)],
) -> ShedRecordRepository:
    return ShedRecordRepository(session)


def get_state_classifier(request: Request) -> StateClassifier | None:
    """未配置分类模型时返回 None，由调用方决定如何降级。"""
    classifier: StateClassifier | None = request.app.state.state_classifier
    return classifier


def get_detector(request: Request) -> Detector:
    detector: Detector = request.app.state.detector
    return detector


def get_judgement_service(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[FrameMetricRepository, Depends(get_metric_repository)],
) -> JudgementService:
    return JudgementService(
        repository,
        baseline_days=settings.baseline_days,
        min_samples=settings.min_baseline_samples,
        z_threshold=settings.robust_z_threshold,
        min_signals=settings.alert_min_signals,
        consecutive_days=settings.alert_consecutive_days,
    )
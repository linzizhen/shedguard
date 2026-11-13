"""照片保留策略：日期边界、子行清理与缺文件容错。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from shedguard_server.config import Settings
from shedguard_server.domain.models import ImageRecord
from shedguard_server.infra.repository import (
    AlertRepository,
    FrameMetricRepository,
    ImageRepository,
    SheddingStateRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.infra.tables import (
    AlertRow,
    Base,
    FrameMetricRow,
    SheddingStateRow,
)
from shedguard_server.services.retention import purge_once

NOW = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _settings(workdir: Path, retention_days: int) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        data_dir=workdir,
        image_retention_days=retention_days,
    )


def _record(image_id: str, *, captured_at: datetime) -> ImageRecord:
    return ImageRecord(
        id=image_id,
        device_id="cam-1",
        rel_path=f"images/2026-05-01/cam-1/{image_id}.jpg",
        byte_size=3,
        sha256=f"{image_id:0<64}"[:64],
        captured_at_utc=captured_at,
        local_date=captured_at.date(),
        received_at_utc=captured_at,
    )


def _seed_image(
    factory: sessionmaker[Session],
    storage: LocalStorage,
    record: ImageRecord,
    *,
    with_children: bool = False,
) -> None:
    with factory() as session:
        ImageRepository(session).add(record)
        if with_children:
            session.add(
                FrameMetricRow(
                    image_id=record.id,
                    device_id=record.device_id,
                    local_date=record.local_date.isoformat(),
                    detected=0,
                    box_json=None,
                    detector_name="null",
                    detector_confidence=None,
                    normalized=0,
                    exposure_scale=1.0,
                    computed_at_utc=NOW.isoformat(),
                    metrics_version="1",
                )
            )
            session.add(
                SheddingStateRow(
                    image_id=record.id,
                    device_id=record.device_id,
                    local_date=record.local_date.isoformat(),
                    state="normal",
                    confidence=None,
                    probabilities_json=None,
                    detector_name="null",
                    classifier_name="null",
                    box_json=None,
                    computed_at_utc=NOW.isoformat(),
                    state_version="1",
                )
            )
            session.add(
                AlertRow(
                    id=f"alert-{record.id}",
                    device_id=record.device_id,
                    pet_id=None,
                    kind="shedding_detected",
                    local_date=record.local_date.isoformat(),
                    state="shedding",
                    image_id=record.id,
                    confidence=None,
                    created_at_utc=NOW.isoformat(),
                    delivered_at_utc=None,
                    read_at_utc=None,
                    push_status="skipped",
                )
            )
            session.commit()
    storage.write_atomic(record.rel_path, b"jpg")


def test_zero_days_keeps_everything(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("old", captured_at=NOW - timedelta(days=30))
    _seed_image(factory, storage, record)

    removed = purge_once(
        session_factory=factory,
        settings=_settings(workdir, 0),
        storage=storage,
        now=NOW,
    )

    assert removed == 0
    assert storage.exists(record.rel_path)
    with factory() as session:
        assert ImageRepository(session).find_by_id(record.id) is not None


def test_image_older_than_retention_is_purged(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("expired", captured_at=NOW - timedelta(days=8))
    _seed_image(factory, storage, record, with_children=True)

    removed = purge_once(
        session_factory=factory,
        settings=_settings(workdir, 7),
        storage=storage,
        now=NOW,
    )

    assert removed == 1
    assert not storage.exists(record.rel_path)
    with factory() as session:
        assert ImageRepository(session).find_by_id(record.id) is None
        assert (
            session.scalar(select(FrameMetricRow).where(FrameMetricRow.image_id == record.id))
            is None
        )
        assert (
            session.scalar(
                select(SheddingStateRow).where(SheddingStateRow.image_id == record.id)
            )
            is None
        )
        alert = session.scalar(select(AlertRow).where(AlertRow.id == f"alert-{record.id}"))
        assert alert is not None
        assert alert.image_id is None


def test_image_exactly_at_cutoff_is_kept(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("edge", captured_at=NOW - timedelta(days=7))
    _seed_image(factory, storage, record)

    removed = purge_once(
        session_factory=factory,
        settings=_settings(workdir, 7),
        storage=storage,
        now=NOW,
    )

    assert removed == 0
    assert storage.exists(record.rel_path)
    with factory() as session:
        assert ImageRepository(session).find_by_id(record.id) is not None


def test_image_one_microsecond_before_cutoff_is_purged(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("just-expired", captured_at=NOW - timedelta(days=7, microseconds=1))
    _seed_image(factory, storage, record)

    removed = purge_once(
        session_factory=factory,
        settings=_settings(workdir, 7),
        storage=storage,
        now=NOW,
    )

    assert removed == 1
    assert not storage.exists(record.rel_path)


def test_missing_file_is_tolerated(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("orphan", captured_at=NOW - timedelta(days=30))
    with factory() as session:
        ImageRepository(session).add(record)

    removed = purge_once(
        session_factory=factory,
        settings=_settings(workdir, 7),
        storage=storage,
        now=NOW,
    )

    assert removed == 1
    with factory() as session:
        assert ImageRepository(session).find_by_id(record.id) is None


def test_second_purge_is_idempotent(workdir: Path) -> None:
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("expired", captured_at=NOW - timedelta(days=8))
    _seed_image(factory, storage, record)
    settings = _settings(workdir, 7)

    first = purge_once(session_factory=factory, settings=settings, storage=storage, now=NOW)
    second = purge_once(session_factory=factory, settings=settings, storage=storage, now=NOW)

    assert (first, second) == (1, 0)


def test_child_repositories_delete_for_image(workdir: Path) -> None:
    """子行删除方法可独立调用，且不依赖图片行是否仍存在。"""
    factory = _session_factory()
    storage = LocalStorage(workdir)
    record = _record("with-children", captured_at=NOW)
    _seed_image(factory, storage, record, with_children=True)

    with factory() as session:
        FrameMetricRepository(session).delete_for_image(record.id)
        SheddingStateRepository(session).delete_for_image(record.id)
        AlertRepository(session).clear_image_reference(record.id)
        session.commit()
        assert (
            session.scalar(select(FrameMetricRow).where(FrameMetricRow.image_id == record.id))
            is None
        )
        assert (
            session.scalar(
                select(SheddingStateRow).where(SheddingStateRow.image_id == record.id)
            )
            is None
        )
        alert = session.scalar(select(AlertRow).where(AlertRow.id == f"alert-{record.id}"))
        assert alert is not None
        assert alert.image_id is None
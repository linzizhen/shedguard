"""照片保留策略：按拍摄时间清理过期图片，先删文件再删数据库行。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.infra.repository import (
    AlertRepository,
    FrameMetricRepository,
    ImageRepository,
    SheddingStateRepository,
)
from shedguard_server.infra.storage import LocalStorage

logger = logging.getLogger("shedguard.retention")


def purge_once(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    storage: LocalStorage,
    now: datetime | None = None,
) -> int:
    """删除过期图片，返回本次删除的行数；`image_retention_days=0` 时什么也不做。

    顺序是硬约束：先删磁盘文件（不存在视为已删，不报错），再删数据库行。
    数据库侧先删 `frame_metrics` 与 `shedding_states` 子行，再删图片行；
    提醒（`alerts`）属于用户历史，只解除 `image_id` 引用，不整条删除。
    """
    if settings.image_retention_days <= 0:
        return 0

    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(days=settings.image_retention_days)
    removed = 0
    with session_factory() as session:
        images = ImageRepository(session)
        metrics = FrameMetricRepository(session)
        states = SheddingStateRepository(session)
        alerts = AlertRepository(session)
        for record in images.list_captured_before(cutoff):
            storage.remove(record.rel_path)
            metrics.delete_for_image(record.id)
            states.delete_for_image(record.id)
            alerts.clear_image_reference(record.id)
            if not images.delete(record.id):  # pragma: no cover - 刚查到又被并发删掉
                continue
            removed += 1
            logger.info(
                "清理过期图片 image_id=%s device_id=%s captured_at=%s",
                record.id,
                record.device_id,
                record.captured_at_utc.isoformat(),
            )
    return removed
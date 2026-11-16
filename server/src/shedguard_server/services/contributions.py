"""数据贡献服务：入队、上传、撤回、打包与偏好设置。

三条铁律（每条都有测试钉住）：
1. 用户没开开关 → 不落盘、不发请求；
2. 没配收件箱 → 不假装成功（保持待上传，不烧重试次数）；
3. 远端不出现宠物名、设备号原值、用户 id、原文件名。
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.contribution import (
    CROP_JPEG_QUALITY,
    DEFAULT_CONTRIBUTION_ENABLED,
    DEFAULT_CROP_PADDING,
    DEFAULT_INCLUDE_FULL,
    DEFAULT_MAX_PENDING,
    DEFAULT_PER_EVENT_LIMIT,
    FULL_JPEG_QUALITY,
    MAX_UPLOAD_ATTEMPTS,
    SAMPLE_FAILED,
    SAMPLE_PENDING,
    SAMPLE_UPLOADED,
    SAMPLE_WITHDRAWN,
    ContributionExport,
    ContributionSample,
    ContributionSetting,
    ContributionStats,
    UploadItem,
    UploadSummary,
    content_hash,
    crop_relative_path,
    device_hash,
    encode_frame,
    export_filename,
    export_relative_path,
    full_relative_path,
    meta_payload,
    remote_paths,
)
from shedguard_server.domain.models import ImageRecord
from shedguard_server.domain.shedding import crop_box, crop_frame
from shedguard_server.errors import InvalidRequestError, NotFoundError
from shedguard_server.infra.contribution_upload import ContributionUploader
from shedguard_server.infra.imaging import decode_image
from shedguard_server.infra.repository import (
    ContributionExportRepository,
    ContributionSampleRepository,
    ContributionSettingRepository,
    FrameMetricRepository,
    ImageRepository,
    PetRepository,
    PushDeviceRepository,
)
from shedguard_server.infra.storage import LocalStorage


class ContributionService:
    """把所有「分享照片」相关动作收在一处。"""

    def __init__(
        self,
        settings: ContributionSettingRepository,
        samples: ContributionSampleRepository,
        exports: ContributionExportRepository,
        pets: PetRepository,
        devices: PushDeviceRepository,
        images: ImageRepository,
        metrics: FrameMetricRepository,
        storage: LocalStorage,
        uploader: ContributionUploader,
        *,
        per_event_limit: int = DEFAULT_PER_EVENT_LIMIT,
        max_pending: int = DEFAULT_MAX_PENDING,
        crop_padding: float = DEFAULT_CROP_PADDING,
        upload_batch_size: int = 20,
    ) -> None:
        self._settings = settings
        self._samples = samples
        self._exports = exports
        self._pets = pets
        self._devices = devices
        self._images = images
        self._metrics = metrics
        self._storage = storage
        self._uploader = uploader
        self._per_event_limit = per_event_limit
        self._max_pending = max_pending
        self._crop_padding = crop_padding
        self._upload_batch_size = upload_batch_size

    # —— 偏好设置 ————————————————————————————————————————————

    def get_settings(self, owner_id: str) -> ContributionSetting:
        found = self._settings.get(owner_id)
        if found is not None:
            return found
        stamp = datetime.now(UTC)
        return ContributionSetting(
            owner_id=owner_id,
            enabled=DEFAULT_CONTRIBUTION_ENABLED,
            include_full=DEFAULT_INCLUDE_FULL,
            created_at_utc=stamp,
            updated_at_utc=stamp,
        )

    def update_settings(
        self,
        owner_id: str,
        *,
        enabled: bool,
        include_full: bool,
        now: datetime | None = None,
    ) -> ContributionSetting:
        current = self._settings.get(owner_id)
        stamp = now or datetime.now(UTC)
        setting = ContributionSetting(
            owner_id=owner_id,
            enabled=enabled,
            include_full=include_full,
            created_at_utc=current.created_at_utc if current is not None else stamp,
            updated_at_utc=stamp,
        )
        return self._settings.upsert(setting)

    # —— 入队 ————————————————————————————————————————————————

    def enqueue_for_event(
        self,
        *,
        device_id: str,
        owner_id: str,
        pet_id: str | None,
        source_image_id: str,
        state: str,
        confidence: float | None,
        local_date: date,
        now: datetime | None = None,
    ) -> ContributionSample | None:
        """蜕皮事件落库后调用；不满足条件就安静地返回 None。"""
        setting = self.get_settings(owner_id)
        if not setting.enabled:
            return None

        existing = self._samples.find_by_source(source_image_id, owner_id)
        if existing is not None:
            return existing
        if self._samples.count_for_event(device_id, local_date) >= self._per_event_limit:
            return None
        if self._samples.count_pending() >= self._max_pending:
            return None

        record = self._images.find_by_id(source_image_id)
        if record is None:
            return None
        metric = self._metrics.find(source_image_id)
        if metric is None or metric.box is None:
            return None

        crop_payload, full_payload = self._render(record, metric.box, setting.include_full)
        digest = content_hash(crop_payload)
        crop_path = crop_relative_path(owner_id, digest)
        full_path = full_relative_path(owner_id, digest) if full_payload is not None else None

        self._storage.write_atomic(crop_path, crop_payload)
        if full_payload is not None and full_path is not None:
            self._storage.write_atomic(full_path, full_payload)

        sample = ContributionSample(
            id=str(uuid4()),
            owner_id=owner_id,
            device_id=device_id,
            pet_id=pet_id,
            source_image_id=source_image_id,
            state=state,
            confidence=confidence,
            local_date=local_date,
            crop_rel_path=crop_path,
            full_rel_path=full_path,
            sha256=digest,
            upload_status=SAMPLE_PENDING,
            upload_attempts=0,
            remote_crop_path=None,
            remote_full_path=None,
            uploaded_at_utc=None,
            created_at_utc=now or datetime.now(UTC),
        )
        return self._samples.add(sample)

    def _render(
        self,
        record: ImageRecord,
        box: tuple[int, int, int, int],
        include_full: bool,
    ) -> tuple[bytes, bytes | None]:
        frame = decode_image(self._storage.read(record.rel_path))
        padded = crop_box(
            box, width=frame.width, height=frame.height, padding=self._crop_padding
        )
        cropped = crop_frame(frame, padded)
        crop_payload = encode_frame(cropped, quality=CROP_JPEG_QUALITY)
        full_payload = (
            encode_frame(frame, quality=FULL_JPEG_QUALITY) if include_full else None
        )
        return crop_payload, full_payload

    # —— 查询 ————————————————————————————————————————————————

    def list_for_owner(self, owner_id: str, *, limit: int = 50) -> list[ContributionSample]:
        return self._samples.list_for_owner(owner_id, limit=limit)

    def get_sample(self, sample_id: str, *, owner_id: str) -> ContributionSample:
        return self._owned(sample_id, owner_id)

    def stats(self, owner_id: str) -> ContributionStats:
        rows = self._samples.list_for_owner(owner_id, limit=1000)
        return ContributionStats(
            total=len(rows),
            pending=sum(1 for row in rows if row.upload_status == SAMPLE_PENDING),
            uploaded=sum(1 for row in rows if row.upload_status == SAMPLE_UPLOADED),
            failed=sum(1 for row in rows if row.upload_status == SAMPLE_FAILED),
            withdrawn=sum(1 for row in rows if row.upload_status == SAMPLE_WITHDRAWN),
        )

    def read_sample(
        self, sample_id: str, *, owner_id: str, full: bool = False
    ) -> tuple[bytes, str]:
        """返回（字节, 媒体类型）；只有用户当初选了整张才有 `full`。"""
        sample = self._owned(sample_id, owner_id)
        rel_path = sample.full_rel_path if full else sample.crop_rel_path
        if rel_path is None:
            raise NotFoundError("这张照片没有保留整张原图")
        if not self._storage.exists(rel_path):
            raise NotFoundError("照片文件已不在本地")
        return self._storage.read(rel_path), "image/jpeg"

    # —— 撤回 ————————————————————————————————————————————————

    def withdraw(
        self, sample_id: str, *, owner_id: str, now: datetime | None = None
    ) -> ContributionSample:
        sample = self._owned(sample_id, owner_id)
        if sample.upload_status == SAMPLE_WITHDRAWN:
            return sample

        remote_paths_to_remove = [
            path
            for path in (sample.remote_crop_path, sample.remote_full_path)
            if path is not None
        ]
        if remote_paths_to_remove:
            self._uploader.delete(remote_paths_to_remove)

        self._storage.remove(sample.crop_rel_path)
        if sample.full_rel_path is not None:
            self._storage.remove(sample.full_rel_path)

        updated = replace(sample, upload_status=SAMPLE_WITHDRAWN, full_rel_path=None)
        return self._samples.update(updated)

    # —— 上传 ————————————————————————————————————————————————

    def upload_pending(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> UploadSummary:
        if not self._uploader.configured:
            waiting = self._samples.count_pending()
            return UploadSummary(skipped=waiting)

        stamp = now or datetime.now(UTC)
        pending = self._samples.list_pending(limit=limit or self._upload_batch_size)
        if not pending:
            return UploadSummary()

        uploaded = 0
        failed_paths: list[str] = []
        for sample in pending:
            outcome = self._upload_one(sample, stamp)
            if outcome:
                uploaded += 1
            else:
                failed_paths.append(sample.crop_rel_path)
        return UploadSummary(
            uploaded=uploaded, failed=len(failed_paths), failed_paths=tuple(failed_paths)
        )

    def _upload_one(self, sample: ContributionSample, now: datetime) -> bool:
        items = self._upload_items(sample)
        if items is None:
            self._samples.update(
                replace(
                    sample,
                    upload_status=SAMPLE_FAILED,
                    upload_attempts=min(sample.upload_attempts + 1, MAX_UPLOAD_ATTEMPTS),
                )
            )
            return False

        result = self._uploader.store(items)
        if result.failed:
            self._samples.update(
                replace(
                    sample,
                    upload_status=SAMPLE_FAILED,
                    upload_attempts=min(sample.upload_attempts + 1, MAX_UPLOAD_ATTEMPTS),
                )
            )
            return False

        crop_remote = items[0].remote_path
        full_remote = sample_full_remote(items)
        self._samples.update(
            replace(
                sample,
                upload_status=SAMPLE_UPLOADED,
                upload_attempts=sample.upload_attempts + 1,
                remote_crop_path=crop_remote,
                remote_full_path=full_remote,
                uploaded_at_utc=now,
            )
        )
        return True

    def _upload_items(self, sample: ContributionSample) -> list[UploadItem] | None:
        if not self._storage.exists(sample.crop_rel_path):
            return None
        paths = remote_paths(
            owner_hash=device_hash(sample.owner_id),
            local_date=sample.local_date,
            digest=sample.sha256,
            include_full=sample.has_full,
        )
        crop_payload = self._storage.read(sample.crop_rel_path)
        meta = meta_payload(
            digest=sample.sha256,
            state=sample.state,
            confidence=sample.confidence,
            local_date=sample.local_date,
            include_full=sample.has_full,
            width=0,
            height=0,
        )
        items = [
            UploadItem(remote_path=paths.crop, payload=crop_payload),
            UploadItem(
                remote_path=paths.meta,
                payload=json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                meta=meta,
            ),
        ]
        if paths.full is not None and sample.full_rel_path is not None:
            if not self._storage.exists(sample.full_rel_path):
                return None
            items.append(
                UploadItem(
                    remote_path=paths.full,
                    payload=self._storage.read(sample.full_rel_path),
                )
            )
        return items

    # —— 本地打包 ————————————————————————————————————————————

    def create_export(
        self, owner_id: str, *, now: datetime | None = None
    ) -> ContributionExport:
        stamp = now or datetime.now(UTC)
        rows = [
            row
            for row in self._samples.list_for_owner(owner_id, limit=1000)
            if row.upload_status != SAMPLE_WITHDRAWN
        ]
        if not rows:
            raise InvalidRequestError("还没有可以打包的照片")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for row in rows:
                if self._storage.exists(row.crop_rel_path):
                    archive.writestr(
                        f"crop/{row.sha256[:12]}.jpg", self._storage.read(row.crop_rel_path)
                    )
                if row.full_rel_path is not None and self._storage.exists(row.full_rel_path):
                    archive.writestr(
                        f"full/{row.sha256[:12]}.jpg", self._storage.read(row.full_rel_path)
                    )
                archive.writestr(
                    f"meta/{row.sha256[:12]}.json",
                    json.dumps(
                        meta_payload(
                            digest=row.sha256,
                            state=row.state,
                            confidence=row.confidence,
                            local_date=row.local_date,
                            include_full=row.has_full,
                            width=0,
                            height=0,
                        ),
                        ensure_ascii=False,
                    ),
                )
        payload = buffer.getvalue()
        filename = export_filename(stamp)
        rel_path = export_relative_path(filename)
        self._storage.write_atomic(rel_path, payload)

        export = ContributionExport(
            id=str(uuid4()),
            owner_id=owner_id,
            filename=filename,
            rel_path=rel_path,
            sample_count=len(rows),
            byte_size=len(payload),
            created_at_utc=stamp,
        )
        return self._exports.add(export)

    def read_export(self, export_id: str, *, owner_id: str) -> tuple[bytes, str]:
        export = self._exports.get(export_id)
        if export is None or export.owner_id != owner_id:
            raise NotFoundError("打包文件不存在")
        if not self._storage.exists(export.rel_path):
            raise NotFoundError("打包文件已不在本地")
        return self._storage.read(export.rel_path), "application/zip"

    def list_exports(self, owner_id: str, *, limit: int = 20) -> list[ContributionExport]:
        return self._exports.list_for_owner(owner_id, limit=limit)

    # —— 小工具 ————————————————————————————————————————————

    def _owned(self, sample_id: str, owner_id: str) -> ContributionSample:
        sample = self._samples.get(sample_id)
        if sample is None or sample.owner_id != owner_id:
            raise NotFoundError("照片不存在")
        return sample


def sample_full_remote(items: Sequence[UploadItem]) -> str | None:
    """从上传项里挑出整张原图那一项（顺序是裁剪、元数据、整张）。"""
    return items[2].remote_path if len(items) > 2 else None


def upload_once(
    *,
    session_factory: sessionmaker[Session],
    config: Settings,
    storage: LocalStorage,
    uploader: ContributionUploader,
    now: datetime | None = None,
) -> UploadSummary:
    """后台一趟：把待上传的样本推给收件箱。

    自开 session，异常交给调用方（后台循环只记日志）。
    """
    with session_factory() as session:
        service = ContributionService(
            settings=ContributionSettingRepository(session),
            samples=ContributionSampleRepository(session),
            exports=ContributionExportRepository(session),
            pets=PetRepository(session),
            devices=PushDeviceRepository(session),
            images=ImageRepository(session),
            metrics=FrameMetricRepository(session),
            storage=storage,
            uploader=uploader,
            per_event_limit=config.contribution_per_event_limit,
            max_pending=config.contribution_max_pending,
            crop_padding=config.contribution_crop_padding,
            upload_batch_size=config.contribution_upload_batch,
        )
        return service.upload_pending(now=now)


__all__ = ["ContributionService", "sample_full_remote", "upload_once"]

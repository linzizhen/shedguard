"""应用层用例：接收一张图片并落盘入库。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from shedguard_server.domain.models import ImageRecord, UploadOutcome
from shedguard_server.domain.naming import build_filename, build_rel_path, sha256_hex
from shedguard_server.domain.timeutil import (
    local_date_of,
    local_moment_of,
    normalize_to_utc,
    parse_rfc3339,
)
from shedguard_server.domain.validation import (
    sniff_image_extension,
    validate_device_id,
    validate_payload_size,
)
from shedguard_server.errors import InvalidRequestError, UnsupportedMediaTypeError
from shedguard_server.infra.repository import ImageRepository
from shedguard_server.infra.storage import LocalStorage


class IngestService:
    """幂等语义：同一内容只落盘入库一次，重复上传返回既有记录。"""

    def __init__(
        self,
        repository: ImageRepository,
        storage: LocalStorage,
        *,
        timezone: ZoneInfo,
        max_upload_bytes: int,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._timezone = timezone
        self._max_upload_bytes = max_upload_bytes

    def ingest(
        self,
        payload: bytes,
        *,
        device_id_raw: str | None,
        captured_at_raw: str | None,
    ) -> UploadOutcome:
        validate_payload_size(len(payload), self._max_upload_bytes)
        extension = sniff_image_extension(payload)
        if extension is None:
            raise UnsupportedMediaTypeError("仅支持 JPEG 与 PNG 图片")
        device_id = validate_device_id(device_id_raw)
        captured_at_utc = self._resolve_captured_at(captured_at_raw)
        sha256 = sha256_hex(payload)

        existing = self._repository.find_by_sha256(sha256)
        if existing is not None:
            return UploadOutcome(record=existing, duplicate=True)

        record = self._build_record(
            payload=payload,
            device_id=device_id,
            captured_at_utc=captured_at_utc,
            sha256=sha256,
            extension=extension,
        )
        self._storage.write_atomic(record.rel_path, payload)
        try:
            self._repository.add(record)
        except IntegrityError:
            # 并发上传同一内容：唯一索引兜底，回查后按幂等命中返回。
            self._storage.remove(record.rel_path)
            winner = self._repository.find_by_sha256(sha256)
            if winner is None:  # pragma: no cover - 约束冲突却查不到，属于数据异常
                raise
            return UploadOutcome(record=winner, duplicate=True)
        return UploadOutcome(record=record, duplicate=False)

    def _resolve_captured_at(self, raw: str | None) -> datetime:
        if raw is None or not raw.strip():
            return datetime.now(UTC)
        try:
            return parse_rfc3339(raw.strip())
        except ValueError as exc:
            raise InvalidRequestError(f"X-Captured-At 不是合法的 RFC 3339 时间: {raw!r}") from exc

    def _build_record(
        self,
        *,
        payload: bytes,
        device_id: str,
        captured_at_utc: datetime,
        sha256: str,
        extension: str,
    ) -> ImageRecord:
        captured_at_utc = normalize_to_utc(captured_at_utc)
        local_moment = local_moment_of(captured_at_utc, self._timezone)
        local_date = local_date_of(captured_at_utc, self._timezone)
        filename = build_filename(local_moment, sha256, extension)
        rel_path = build_rel_path(local_date, device_id, filename)
        return ImageRecord(
            id=str(uuid.uuid4()),
            device_id=device_id,
            rel_path=rel_path,
            byte_size=len(payload),
            sha256=sha256,
            captured_at_utc=captured_at_utc,
            local_date=local_date,
            received_at_utc=datetime.now(UTC),
        )
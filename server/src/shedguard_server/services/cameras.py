"""应用层：摄像头接入（注册、测试、抓拍、失败兜底）。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from shedguard_server.config import Settings
from shedguard_server.domain.alerts import ALERT_KIND_DEVICE_SILENT  # noqa: F401
from shedguard_server.domain.camera import (
    ALERT_KIND_CAMERA_OFFLINE,
    CAMERA_PROVIDER_EZVIZ,
    CAMERA_PROVIDER_RTSP,
    MAX_LABEL_LENGTH,
    Camera,
    CameraError,
    CameraSource,
    CameraTestResult,
    split_secret_config,
    status_for_failure,
)
from shedguard_server.domain.models import UploadOutcome
from shedguard_server.domain.push import PushGateway
from shedguard_server.domain.timeutil import local_date_of, normalize_to_utc
from shedguard_server.errors import CameraUnavailableError, InvalidRequestError, NotFoundError
from shedguard_server.infra.camera_sources import build_camera_source, grab_frame_from_url
from shedguard_server.infra.crypto import SecretBoxError, SecretBoxLike, build_secret_box
from shedguard_server.infra.repository import (
    AlertRepository,
    CameraRepository,
    ImageRepository,
    PetRepository,
    PushDeviceRepository,
)
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.services.alerts import AlertService
from shedguard_server.services.ingest import IngestService

PROVIDERS = (CAMERA_PROVIDER_EZVIZ, CAMERA_PROVIDER_RTSP)


def _utc_iso(moment: datetime) -> str:
    """与设备上传保持同一种时间写法。"""
    return normalize_to_utc(moment).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    """一次手动抓拍的结果：拿到图就走完入库流水线。"""

    camera_id: str
    image: UploadOutcome
    took_ms: int


class CameraService:
    """一个摄像头只负责交出一张 JPEG，其余交给既有流水线。"""

    def __init__(
        self,
        cameras: CameraRepository,
        pets: PetRepository,
        ingest: IngestService,
        box: SecretBoxLike,
        *,
        timezone: ZoneInfo,
        timeout_seconds: float = 15.0,
        max_failures: int = 3,
        ezviz_api: object | None = None,
        grabber: object = grab_frame_from_url,
    ) -> None:
        self._cameras = cameras
        self._pets = pets
        self._ingest = ingest
        self._box = box
        self._timezone = timezone
        self._timeout_seconds = timeout_seconds
        self._max_failures = max_failures
        self._ezviz_api = ezviz_api
        self._grabber = grabber

    # ---- 查询与写入 ---------------------------------------------------

    def list(self, owner_id: str) -> list[Camera]:
        return self._cameras.list_for_owner(owner_id)

    def get(self, camera_id: str, *, owner_id: str) -> Camera:
        camera = self._cameras.get(camera_id, owner_id=owner_id)
        if camera is None:
            raise NotFoundError(f"找不到摄像头: {camera_id}")
        return camera

    def create(
        self,
        *,
        owner_id: str,
        provider: str,
        label: str,
        pet_id: str | None = None,
        config: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> Camera:
        if provider not in PROVIDERS:
            raise InvalidRequestError(f"暂不支持的摄像头类型: {provider}")
        clean_label = label.strip()
        if not clean_label:
            raise InvalidRequestError("给摄像头起个名字吧")
        if len(clean_label) > MAX_LABEL_LENGTH:
            raise InvalidRequestError(f"名字太长了，最多 {MAX_LABEL_LENGTH} 个字")
        if pet_id is not None and self._pets.find(pet_id, owner_id) is None:
            raise InvalidRequestError("找不到这只宠物")

        public, private = split_secret_config(provider, config or {})
        moment = normalize_to_utc(now or datetime.now(UTC))
        camera = Camera(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            pet_id=pet_id,
            provider=provider,
            label=clean_label,
            config=public,
            secret_enc=self._encrypt(private),
            enabled=True,
            status="never_tested",
            last_error="",
            last_frame_at_utc=None,
            consecutive_failures=0,
            created_at_utc=_utc_iso(moment),
            updated_at_utc=_utc_iso(moment),
        )
        self._cameras.add(camera)
        return camera

    def update(
        self,
        camera_id: str,
        *,
        owner_id: str,
        label: str | None = None,
        pet_id: str | None = None,
        update_pet: bool = False,
        enabled: bool | None = None,
        config: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> Camera:
        camera = self.get(camera_id, owner_id=owner_id)
        moment = normalize_to_utc(now or datetime.now(UTC))

        changes: dict[str, object] = {"updated_at_utc": _utc_iso(moment)}
        if label is not None:
            clean_label = label.strip()
            if not clean_label:
                raise InvalidRequestError("给摄像头起个名字吧")
            if len(clean_label) > MAX_LABEL_LENGTH:
                raise InvalidRequestError(f"名字太长了，最多 {MAX_LABEL_LENGTH} 个字")
            changes["label"] = clean_label
        if update_pet:
            if pet_id is not None and self._pets.find(pet_id, owner_id) is None:
                raise InvalidRequestError("找不到这只宠物")
            changes["pet_id"] = pet_id
        if enabled is not None:
            changes["enabled"] = enabled
        if config is not None:
            public, private = split_secret_config(camera.provider, config)
            changes["config"] = public
            if private:
                changes["secret_enc"] = self._encrypt(private)

        updated = replace(camera, **changes)  # type: ignore[arg-type]
        self._cameras.save(updated)
        return updated

    def delete(self, camera_id: str, *, owner_id: str) -> None:
        camera = self.get(camera_id, owner_id=owner_id)
        self._cameras.delete(camera.id)

    # ---- 取帧 ---------------------------------------------------------

    def test(
        self, camera_id: str, *, owner_id: str, now: datetime | None = None
    ) -> CameraTestResult:
        """连一下试试：只验证能不能取到画面，不入库。"""
        camera = self.get(camera_id, owner_id=owner_id)
        started = time.monotonic()
        try:
            source = self._source(camera)
            source.fetch_frame()
        except CameraError as exc:
            took_ms = int((time.monotonic() - started) * 1000)
            self._mark_failure(camera, exc, now=now)
            return CameraTestResult(ok=False, kind=exc.kind, detail=exc.detail, took_ms=took_ms)
        except SecretBoxError as exc:
            raise InvalidRequestError(str(exc)) from exc
        took_ms = int((time.monotonic() - started) * 1000)
        self._mark_success(camera, now=now)
        return CameraTestResult(ok=True, kind="ok", detail="能取到画面", took_ms=took_ms)

    def snapshot(
        self, camera_id: str, *, owner_id: str, now: datetime | None = None
    ) -> SnapshotResult:
        """抓一帧并入库；后续分析由上传流水线接着做。"""
        camera = self.get(camera_id, owner_id=owner_id)
        moment = normalize_to_utc(now or datetime.now(UTC))
        try:
            source = self._source(camera)
            payload = source.fetch_frame()
        except SecretBoxError as exc:
            raise InvalidRequestError(str(exc)) from exc
        except CameraError as exc:
            self._mark_failure(camera, exc, now=moment)
            raise CameraUnavailableError(exc.detail) from exc

        outcome = self._ingest.ingest(
            payload,
            device_id_raw=camera.device_id,
            captured_at_raw=_utc_iso(moment),
        )
        self._mark_success(camera, frame_at=moment, now=moment)
        return SnapshotResult(camera_id=camera.id, image=outcome, took_ms=0)

    # ---- 内部 ---------------------------------------------------------

    def _source(self, camera: Camera) -> CameraSource:
        secrets = self._box.decrypt(camera.secret_enc) if camera.secret_enc else {}
        return build_camera_source(
            camera,
            secrets,
            timeout_seconds=self._timeout_seconds,
            ezviz_api=self._ezviz_api,  # type: ignore[arg-type]
            grabber=self._grabber,  # type: ignore[arg-type]
        )

    def _encrypt(self, private: dict[str, str]) -> str:
        if not private:
            return ""
        try:
            return self._box.encrypt(private)
        except SecretBoxError as exc:
            raise InvalidRequestError(str(exc)) from exc

    def _mark_success(
        self, camera: Camera, *, frame_at: datetime | None = None, now: datetime | None = None
    ) -> None:
        moment = normalize_to_utc(now or datetime.now(UTC))
        self._cameras.save(
            replace(
                camera,
                status="ok",
                last_error="",
                consecutive_failures=0,
                last_frame_at_utc=(
                    _utc_iso(frame_at) if frame_at is not None else camera.last_frame_at_utc
                ),
                updated_at_utc=_utc_iso(moment),
            )
        )

    def _mark_failure(
        self, camera: Camera, exc: CameraError, *, now: datetime | None = None
    ) -> Camera:
        moment = normalize_to_utc(now or datetime.now(UTC))
        updated = replace(
            camera,
            status=status_for_failure(exc.kind),
            last_error=exc.detail,
            consecutive_failures=camera.consecutive_failures + 1,
            updated_at_utc=_utc_iso(moment),
        )
        self._cameras.save(updated)
        return updated


def _build_ingest(session: Session, *, settings: Settings, storage: LocalStorage) -> IngestService:
    return IngestService(
        ImageRepository(session),
        storage,
        timezone=ZoneInfo(settings.timezone),
        max_upload_bytes=settings.max_upload_bytes,
    )


def poll_once(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    storage: LocalStorage,
    gateway: PushGateway,
    now: datetime | None = None,
) -> int:
    """定时抓拍一轮：成功入库即计数，连续失败到阈值就发一条提醒。"""
    if not settings.camera_enabled:
        return 0

    moment = normalize_to_utc(now or datetime.now(UTC))
    tz = ZoneInfo(settings.timezone)
    ingested = 0

    with session_factory() as session:
        cameras = CameraRepository(session)
        pets = PetRepository(session)
        alerts = AlertRepository(session)
        devices = PushDeviceRepository(session)
        box = build_secret_box(settings.secret_key)
        service = CameraService(
            cameras,
            pets,
            _build_ingest(session, settings=settings, storage=storage),
            box,
            timezone=tz,
            timeout_seconds=settings.camera_timeout_seconds,
            max_failures=settings.camera_max_failures,
        )
        alert_service = AlertService(alerts, devices, gateway)

        for camera in cameras.list_enabled():
            try:
                result = service.snapshot(camera.id, owner_id=camera.owner_id, now=moment)
            except (CameraUnavailableError, InvalidRequestError):
                failed = cameras.get(camera.id)
                if (
                    failed is not None
                    and failed.consecutive_failures >= settings.camera_max_failures
                ):
                    _alert_offline(alert_service, failed, moment=moment, tz=tz)
                continue
            if not result.image.duplicate:
                ingested += 1

    return ingested


def _alert_offline(
    service: AlertService, camera: Camera, *, moment: datetime, tz: ZoneInfo
) -> None:
    """同一天只提醒一次；唯一键由 (device_id, local_date, kind) 保证。"""
    try:
        alert = service.create_alert(
            device_id=camera.device_id,
            local_date=local_date_of(moment, tz),
            kind=ALERT_KIND_CAMERA_OFFLINE,
            pet_id=camera.pet_id,
            now=moment,
        )
    except Exception:
        return
    if alert is not None:
        service.deliver(alert)


def scan_interval_seconds(settings: Settings) -> int:
    return settings.camera_poll_minutes * 60
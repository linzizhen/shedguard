"""数据贡献纯逻辑层的单元测试。"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

import cv2
import numpy as np
import pytest

from shedguard_server.domain.contribution import (
    META_FIELDS,
    SAMPLE_STATUSES,
    ContributionSample,
    content_hash,
    crop_relative_path,
    device_hash,
    encode_frame,
    export_filename,
    export_relative_path,
    full_relative_path,
    meta_path_for,
    meta_payload,
    remote_paths,
)
from shedguard_server.domain.imaging import ImageFrame

DIGEST = "0123456789abcdef" * 4


def _sample(**overrides: object) -> ContributionSample:
    base: dict[str, object] = {
        "id": "s1",
        "owner_id": "dev",
        "device_id": "dev-1",
        "pet_id": None,
        "source_image_id": "img-1",
        "state": "shedding",
        "confidence": 0.9,
        "local_date": date(2026, 11, 16),
        "crop_rel_path": "contributions/dev/crop/0123456789ab.jpg",
        "full_rel_path": None,
        "sha256": DIGEST,
        "upload_status": "pending",
        "upload_attempts": 0,
        "remote_crop_path": None,
        "remote_full_path": None,
        "uploaded_at_utc": None,
        "created_at_utc": datetime(2026, 11, 16, tzinfo=UTC),
    }
    base.update(overrides)
    return ContributionSample(**base)  # type: ignore[arg-type]


class TestDeviceHash:
    def test_is_stable_and_short(self) -> None:
        first = device_hash("gecko-eye-01")

        assert first == device_hash("gecko-eye-01")
        assert len(first) == 12

    def test_differs_between_devices(self) -> None:
        assert device_hash("a") != device_hash("b")

    def test_empty_is_unknown(self) -> None:
        assert device_hash("") == "unknown"


class TestPaths:
    def test_local_paths_keep_owner_prefix(self) -> None:
        assert crop_relative_path("dev", DIGEST) == "contributions/dev/crop/0123456789ab.jpg"
        assert full_relative_path("dev", DIGEST) == "contributions/dev/full/0123456789ab.jpg"
        assert export_relative_path("x.zip") == "exports/x.zip"

    def test_remote_paths_omit_full_by_default(self) -> None:
        paths = remote_paths(
            owner_hash="abc123", local_date=date(2026, 11, 16), digest=DIGEST, include_full=False
        )

        assert paths.crop == "abc123/2026-11-16/0123456789ab.jpg"
        assert paths.meta == "abc123/2026-11-16/0123456789ab.json"
        assert paths.full is None

    def test_remote_paths_include_full_when_asked(self) -> None:
        paths = remote_paths(
            owner_hash="abc123", local_date=date(2026, 11, 16), digest=DIGEST, include_full=True
        )

        assert paths.full == "abc123/2026-11-16/0123456789ab.full.jpg"

    def test_export_filename_shape(self) -> None:
        name = export_filename(datetime(2026, 11, 16, 9, 30, 0, tzinfo=UTC))

        assert re.fullmatch(r"contribution-\d{8}T\d{6}-[0-9a-f]{6}\.zip", name)

    def test_meta_path_for_mirrors_remote_paths(self) -> None:
        """撤回要用它还原元数据路径，必须和 remote_paths() 拼出来的完全一致。"""
        paths = remote_paths(
            owner_hash="abc123", local_date=date(2026, 11, 16), digest=DIGEST, include_full=True
        )

        assert meta_path_for(paths.crop) == paths.meta
        assert meta_path_for(paths.full or "") == "abc123/2026-11-16/0123456789ab.full.json"

    def test_meta_path_for_handles_no_suffix(self) -> None:
        assert meta_path_for("a/b/0") == "a/b/0.json"


class TestContentHash:
    def test_matches_sha256(self) -> None:
        assert content_hash(b"abc") == content_hash(b"abc")
        assert content_hash(b"abc") != content_hash(b"abd")
        assert len(content_hash(b"abc")) == 64


class TestMetaPayload:
    def test_only_whitelisted_fields(self) -> None:
        payload = meta_payload(
            digest=DIGEST,
            state="shedding",
            confidence=0.9,
            local_date=date(2026, 11, 16),
            include_full=False,
            width=640,
            height=480,
        )

        assert set(payload) == set(META_FIELDS)
        assert payload["sha12"] == "0123456789ab"
        assert payload["local_date"] == "2026-11-16"
        assert payload["has_full"] is False

    def test_never_leaks_identity(self) -> None:
        payload = meta_payload(
            digest=DIGEST,
            state="normal",
            confidence=None,
            local_date=date(2026, 11, 16),
            include_full=True,
            width=1,
            height=1,
        )

        joined = " ".join(str(value) for value in payload.values())
        assert "dev" not in joined
        assert "小橘子" not in joined


class TestEncodeFrame:
    def test_returns_decodable_jpeg(self) -> None:
        rgb = np.full((64, 48, 3), 120, dtype=np.uint8)
        frame = ImageFrame(width=48, height=64, rgb=rgb)

        payload = encode_frame(frame, quality=88)

        assert payload[:2] == b"\xff\xd8"
        decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None
        assert decoded.shape[0] == 64
        assert decoded.shape[1] == 48

    def test_quality_changes_size(self) -> None:
        rng = np.random.default_rng(7)
        rgb = rng.integers(0, 255, size=(120, 160, 3), dtype=np.uint8)
        frame = ImageFrame(width=160, height=120, rgb=rgb)

        tiny = encode_frame(frame, quality=20)
        large = encode_frame(frame, quality=95)

        assert len(tiny) < len(large)


class TestSampleValidation:
    def test_accepts_known_status(self) -> None:
        sample = _sample(upload_status="uploaded")

        assert sample.upload_status == "uploaded"
        assert sample.upload_attempts == 0

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValueError):
            _sample(upload_status="sent")

    def test_rejects_negative_attempts(self) -> None:
        with pytest.raises(ValueError):
            _sample(upload_attempts=-1)

    def test_has_full_flag(self) -> None:
        assert _sample(full_rel_path="contributions/dev/full/x.jpg").has_full is True
        assert _sample().has_full is False

    def test_status_set_is_complete(self) -> None:
        assert {"pending", "uploaded", "failed", "withdrawn"} == SAMPLE_STATUSES

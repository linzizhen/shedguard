"""本地存储的单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from shedguard_server.errors import StorageUnavailableError
from shedguard_server.infra.storage import LocalStorage


def test_write_then_read_roundtrip(workdir: Path) -> None:
    storage = LocalStorage(workdir)

    storage.write_atomic("images/2026-11-02/cam/120000_abcd1234.jpg", b"payload")

    assert storage.exists("images/2026-11-02/cam/120000_abcd1234.jpg")
    assert storage.read("images/2026-11-02/cam/120000_abcd1234.jpg") == b"payload"


def test_write_leaves_no_temp_file(workdir: Path) -> None:
    storage = LocalStorage(workdir)
    storage.write_atomic("images/a.jpg", b"x")

    leftovers = [item.name for item in (workdir / "images").iterdir() if item.name.endswith(".tmp")]
    assert leftovers == []


def test_resolve_rejects_path_escape(workdir: Path) -> None:
    storage = LocalStorage(workdir)

    with pytest.raises(StorageUnavailableError):
        storage.resolve("../outside.jpg")


def test_read_missing_file_raises(workdir: Path) -> None:
    storage = LocalStorage(workdir)

    with pytest.raises(StorageUnavailableError):
        storage.read("images/none.jpg")


def test_write_failure_is_wrapped(workdir: Path) -> None:
    """目标路径被同名目录占用时，写文件必然失败并被转成存储不可用。"""
    storage = LocalStorage(workdir)
    blocker = workdir / "images" / "blocked.jpg"
    blocker.mkdir(parents=True)

    with pytest.raises(StorageUnavailableError):
        storage.write_atomic("images/blocked.jpg", b"x")


def test_remove_is_idempotent(workdir: Path) -> None:
    storage = LocalStorage(workdir)
    storage.write_atomic("images/a.jpg", b"x")

    storage.remove("images/a.jpg")
    storage.remove("images/a.jpg")

    assert not storage.exists("images/a.jpg")
"""pytest 全局配置与共享 fixture。

本机沙箱不允许访问系统临时目录（pytest 自带的 `tmp_path` 会在 scandir / rmdir
阶段被拒绝），因此统一使用仓库内 `.tmp/` 下的临时目录。
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = PROJECT_ROOT.parent / ".tmp"


@pytest.fixture()
def workdir() -> Iterator[Path]:
    """每个测试独占的可写临时目录，测试结束即删除。"""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"test-{uuid.uuid4().hex[:12]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
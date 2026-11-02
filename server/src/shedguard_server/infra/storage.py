"""本地文件存储：临时文件 + 原子重命名，路径由服务端生成。"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from shedguard_server.errors import StorageUnavailableError


class LocalStorage:
    """以数据根目录为界的文件存储。"""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def resolve(self, rel_path: str) -> Path:
        """把相对路径解析为绝对路径，并确保不逃出数据根目录。"""
        candidate = (self._root / rel_path).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            msg = f"非法存储路径: {rel_path}"
            raise StorageUnavailableError(msg)
        return candidate

    def exists(self, rel_path: str) -> bool:
        return self.resolve(rel_path).is_file()

    def write_atomic(self, rel_path: str, payload: bytes) -> None:
        """先写同目录临时文件，再原子重命名；失败时清理临时文件。"""
        target = self.resolve(rel_path)
        temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(payload)
            os.replace(temp, target)
        except OSError as exc:
            msg = f"写入图片失败: {rel_path}"
            raise StorageUnavailableError(msg) from exc
        finally:
            temp.unlink(missing_ok=True)

    def read(self, rel_path: str) -> bytes:
        try:
            return self.resolve(rel_path).read_bytes()
        except OSError as exc:
            msg = f"读取图片失败: {rel_path}"
            raise StorageUnavailableError(msg) from exc

    def remove(self, rel_path: str) -> None:
        """删除文件，不存在时静默返回；用于入库失败后的补偿。"""
        with contextlib.suppress(OSError):
            self.resolve(rel_path).unlink(missing_ok=True)
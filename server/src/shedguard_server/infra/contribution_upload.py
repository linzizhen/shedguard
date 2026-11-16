"""数据贡献的收件箱写入器。

对外只有一个 `ContributionUploader` 协议：服务层只管把「要写哪些文件」交给它，
具体是写 HuggingFace 仓库、写本地目录还是干脆不写，都在这里决定。
默认实现 `NoopUploader` 会**明确失败**而不是假装成功——没配收件箱时不能悄悄丢数据。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from huggingface_hub import CommitOperation, CommitOperationAdd, HfApi

from shedguard_server.domain.contribution import (
    UploadBatchResult,
    UploadItem,
)

DEFAULT_REPO_TYPE = "dataset"


class UploadApi(Protocol):
    """`HfApi` 里我们真正用到的那两个方法；抽出来是为了能塞假实现。"""

    def create_commit(
        self,
        repo_id: str,
        operations: Sequence[CommitOperation],
        *,
        commit_message: str,
        repo_type: str | None = None,
    ) -> object: ...

    def delete_file(
        self,
        path_in_repo: str,
        repo_id: str,
        *,
        commit_message: str | None = None,
        repo_type: str | None = None,
    ) -> object: ...


class ContributionUploader(Protocol):
    """把一批文件写进收件箱，并能按路径撤回。"""

    @property
    def name(self) -> str: ...

    @property
    def configured(self) -> bool:
        """收件箱是否真的可用；False 时服务层只能把样本留在待上传。"""
        ...

    def store(self, items: Sequence[UploadItem]) -> UploadBatchResult: ...

    def delete(self, remote_paths: Sequence[str]) -> None: ...


class NoopUploader:
    """没配置收件箱时的占位实现：所有项都算失败。"""

    def __init__(self, reason: str = "未配置收件箱") -> None:
        self._reason = reason

    @property
    def name(self) -> str:
        return "noop"

    @property
    def configured(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return self._reason

    def store(self, items: Sequence[UploadItem]) -> UploadBatchResult:
        return UploadBatchResult(uploaded=0, failed=tuple(item.remote_path for item in items))

    def delete(self, remote_paths: Sequence[str]) -> None:
        return None


class HuggingFaceUploader:
    """把样本写进 HuggingFace 数据集仓库（一次 commit，尽量少产生历史）。"""

    def __init__(
        self,
        repo_id: str,
        token: str,
        *,
        repo_type: str = DEFAULT_REPO_TYPE,
        api: UploadApi | None = None,
    ) -> None:
        self._repo_id = repo_id
        self._repo_type = repo_type
        self._api: UploadApi = api if api is not None else HfApi(token=token)

    @property
    def name(self) -> str:
        return f"hf:{self._repo_id}"

    @property
    def configured(self) -> bool:
        return True

    def store(self, items: Sequence[UploadItem]) -> UploadBatchResult:
        if not items:
            return UploadBatchResult()

        operations: list[CommitOperationAdd] = [
            CommitOperationAdd(path_in_repo=item.remote_path, path_or_fileobj=item.payload)
            for item in items
        ]
        try:
            self._api.create_commit(
                self._repo_id,
                operations,
                commit_message=f"add {len(items)} contribution sample(s)",
                repo_type=self._repo_type,
            )
        except Exception:
            return UploadBatchResult(
                uploaded=0, failed=tuple(item.remote_path for item in items)
            )
        return UploadBatchResult(uploaded=len(items))

    def delete(self, remote_paths: Sequence[str]) -> None:
        """尽力删除；删不掉不回滚本地（撤回是「不再保留」，不是「保证干净」）。"""
        for path in remote_paths:
            try:
                self._api.delete_file(
                    path,
                    self._repo_id,
                    commit_message=f"remove {path}",
                    repo_type=self._repo_type,
                )
            except Exception:
                continue


def build_contribution_uploader(
    *, enabled: bool, repo_id: str, token: str, repo_type: str = DEFAULT_REPO_TYPE
) -> ContributionUploader:
    """按配置挑一个写入器：没开开关或没配仓库，一律用 `NoopUploader`。"""
    if not enabled or not repo_id:
        return NoopUploader()
    return HuggingFaceUploader(repo_id, token, repo_type=repo_type)


__all__ = [
    "ContributionUploader",
    "HuggingFaceUploader",
    "NoopUploader",
    "UploadApi",
    "build_contribution_uploader",
]

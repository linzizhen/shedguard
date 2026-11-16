"""收件箱写入器的单元测试（用假 API，不碰网络）。"""

from __future__ import annotations

from collections.abc import Sequence

from huggingface_hub import CommitOperation

from shedguard_server.domain.contribution import UploadItem
from shedguard_server.infra.contribution_upload import (
    HuggingFaceUploader,
    NoopUploader,
    build_contribution_uploader,
)


class _FakeApi:
    """记录调用的假 HfApi。"""

    def __init__(self, *, fail_commit: bool = False, fail_delete: bool = False) -> None:
        self.commits: list[tuple[str, list[tuple[str, bytes]], str]] = []
        self.deleted: list[str] = []
        self._fail_commit = fail_commit
        self._fail_delete = fail_delete

    def create_commit(
        self,
        repo_id: str,
        operations: Sequence[CommitOperation],
        *,
        commit_message: str,
        repo_type: str | None = None,
    ) -> object:
        if self._fail_commit:
            raise RuntimeError("boom")
        entries: list[tuple[str, bytes]] = []
        for operation in operations:
            assert hasattr(operation, "path_in_repo")
            entries.append((operation.path_in_repo, repr(operation).encode("utf-8")))
        self.commits.append((repo_id, entries, commit_message))
        return object()

    def delete_file(
        self,
        path_in_repo: str,
        repo_id: str,
        *,
        commit_message: str | None = None,
        repo_type: str | None = None,
    ) -> object:
        if self._fail_delete:
            raise RuntimeError("boom")
        self.deleted.append(path_in_repo)
        return object()


def _items(count: int = 2) -> list[UploadItem]:
    return [
        UploadItem(remote_path=f"a/b/{index}.jpg", payload=b"x", meta=None)
        for index in range(count)
    ]


class TestNoopUploader:
    def test_is_not_configured(self) -> None:
        uploader = NoopUploader()

        assert uploader.configured is False
        assert uploader.name == "noop"
        assert uploader.reason == "未配置收件箱"

    def test_store_fails_every_item(self) -> None:
        result = NoopUploader().store(_items(3))

        assert result.uploaded == 0
        assert result.failed == ("a/b/0.jpg", "a/b/1.jpg", "a/b/2.jpg")

    def test_delete_is_noop(self) -> None:
        NoopUploader().delete(["x"])  # 不抛异常即通过


class TestHuggingFaceUploader:
    def test_store_commits_once(self) -> None:
        api = _FakeApi()
        uploader = HuggingFaceUploader("me/inbox", "tok", api=api)

        result = uploader.store(_items(2))

        assert uploader.configured is True
        assert uploader.name == "hf:me/inbox"
        assert result.uploaded == 2
        assert result.failed == ()
        assert len(api.commits) == 1
        repo_id, entries, message = api.commits[0]
        assert repo_id == "me/inbox"
        assert [path for path, _ in entries] == ["a/b/0.jpg", "a/b/1.jpg"]
        assert "2 contribution" in message

    def test_store_without_items_short_circuits(self) -> None:
        api = _FakeApi()

        result = HuggingFaceUploader("me/inbox", "tok", api=api).store([])

        assert result.uploaded == 0
        assert api.commits == []

    def test_store_failure_marks_all_failed(self) -> None:
        api = _FakeApi(fail_commit=True)

        result = HuggingFaceUploader("me/inbox", "tok", api=api).store(_items(2))

        assert result.uploaded == 0
        assert result.failed == ("a/b/0.jpg", "a/b/1.jpg")

    def test_delete_calls_api(self) -> None:
        api = _FakeApi()

        HuggingFaceUploader("me/inbox", "tok", api=api).delete(["a/b/0.jpg", "a/b/1.jpg"])

        assert api.deleted == ["a/b/0.jpg", "a/b/1.jpg"]

    def test_delete_swallows_errors(self) -> None:
        api = _FakeApi(fail_delete=True)

        HuggingFaceUploader("me/inbox", "tok", api=api).delete(["a/b/0.jpg"])

        assert api.deleted == []


class TestBuildUploader:
    def test_disabled_returns_noop(self) -> None:
        uploader = build_contribution_uploader(enabled=False, repo_id="me/inbox", token="tok")

        assert isinstance(uploader, NoopUploader)

    def test_without_repo_returns_noop(self) -> None:
        uploader = build_contribution_uploader(enabled=True, repo_id="", token="tok")

        assert isinstance(uploader, NoopUploader)

    def test_enabled_with_repo_returns_hf(self) -> None:
        uploader = build_contribution_uploader(enabled=True, repo_id="me/inbox", token="tok")

        assert isinstance(uploader, HuggingFaceUploader)
        assert uploader.name == "hf:me/inbox"

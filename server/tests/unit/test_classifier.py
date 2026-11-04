"""ONNX 蜕皮状态分类器的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState
from shedguard_server.errors import StorageUnavailableError
from shedguard_server.infra.classifier import OnnxStateClassifier, load_labels


def _frame(size: int = 32) -> ImageFrame:
    return ImageFrame(
        width=size,
        height=size,
        rgb=np.full((size, size, 3), 128, dtype=np.uint8),
    )


class _FakeSession:
    """只回放预设输出，不碰 onnxruntime。"""

    def __init__(self, output: Any, *, inputs: list[Any] | None = None) -> None:
        self._output = output
        self._inputs = inputs if inputs is not None else [SimpleNamespace(name="images")]

    def get_inputs(self) -> list[Any]:
        return self._inputs

    def run(self, _names: Any, _feeds: Any) -> list[Any]:
        return [self._output]


def _write_labels(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestLoadLabels:
    def test_reads_a_dict_payload(self, workdir: Path) -> None:
        path = _write_labels(
            workdir / "m.labels.json",
            {"labels": ["normal", "shedding"], "input_size": 256},
        )

        labels, input_size = load_labels(path)

        assert labels == ("normal", "shedding")
        assert input_size == 256

    def test_reads_a_bare_list(self, workdir: Path) -> None:
        path = _write_labels(workdir / "m.labels.json", ["normal", "opaque", "shedding"])

        labels, input_size = load_labels(path)

        assert labels == ("normal", "opaque", "shedding")
        assert input_size == 224

    def test_rejects_a_missing_file(self, workdir: Path) -> None:
        with pytest.raises(StorageUnavailableError, match="分类标签不存在"):
            load_labels(workdir / "absent.labels.json")

    def test_rejects_malformed_json(self, workdir: Path) -> None:
        path = workdir / "m.labels.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(StorageUnavailableError, match="无法解析"):
            load_labels(path)

    def test_rejects_an_empty_list(self, workdir: Path) -> None:
        path = _write_labels(workdir / "m.labels.json", [])

        with pytest.raises(StorageUnavailableError, match="格式不对"):
            load_labels(path)

    def test_rejects_an_unknown_label(self, workdir: Path) -> None:
        path = _write_labels(workdir / "m.labels.json", ["normal", "molting"])

        with pytest.raises(StorageUnavailableError, match="未知的蜕皮状态标签"):
            load_labels(path)

    def test_rejects_unknown_as_a_class(self, workdir: Path) -> None:
        path = _write_labels(workdir / "m.labels.json", ["normal", "unknown"])

        with pytest.raises(StorageUnavailableError, match="不能是 unknown"):
            load_labels(path)


class TestFromPath:
    def test_rejects_a_missing_model(self, workdir: Path) -> None:
        with pytest.raises(StorageUnavailableError, match="分类模型不存在"):
            OnnxStateClassifier.from_path(workdir / "absent.onnx")

    def test_checks_labels_before_loading_the_model(self, workdir: Path) -> None:
        model = workdir / "m.onnx"
        model.write_bytes(b"not a real model")

        with pytest.raises(StorageUnavailableError, match="分类标签不存在"):
            OnnxStateClassifier.from_path(model)

    def test_wires_the_session_and_labels(self, workdir: Path, monkeypatch: Any) -> None:
        import onnxruntime

        model = workdir / "gecko-state.onnx"
        model.write_bytes(b"fake")
        _write_labels(
            workdir / "gecko-state.labels.json",
            {"labels": ["normal", "shedding"], "input_size": 256},
        )
        fake = _FakeSession(np.array([[1.0, 2.0]], dtype=np.float32))
        monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_a, **_k: fake)

        classifier = OnnxStateClassifier.from_path(model)

        assert classifier.name == "onnx:gecko-state"
        assert classifier.input_name == "images"
        assert classifier.labels == ("normal", "shedding")
        assert classifier.input_size == 256

    def test_rejects_a_model_without_inputs(self, workdir: Path, monkeypatch: Any) -> None:
        import onnxruntime

        model = workdir / "m.onnx"
        model.write_bytes(b"fake")
        _write_labels(workdir / "m.labels.json", ["normal"])
        fake = _FakeSession(None, inputs=[])
        monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_a, **_k: fake)

        with pytest.raises(StorageUnavailableError, match="没有输入节点"):
            OnnxStateClassifier.from_path(model)

    def test_reports_a_session_that_fails_to_load(
        self, workdir: Path, monkeypatch: Any
    ) -> None:
        import onnxruntime

        model = workdir / "m.onnx"
        model.write_bytes(b"fake")
        _write_labels(workdir / "m.labels.json", ["normal"])

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("bad model")

        monkeypatch.setattr(onnxruntime, "InferenceSession", _boom)

        with pytest.raises(StorageUnavailableError, match="分类模型加载失败"):
            OnnxStateClassifier.from_path(model)


class TestClassify:
    def _classifier(self, output: Any, *, labels: tuple[str, ...] | None = None) -> Any:
        return OnnxStateClassifier(
            session=_FakeSession(output),
            input_name="input",
            name="onnx:test",
            labels=labels or ("normal", "shedding"),
            input_size=224,
        )

    def test_picks_the_highest_logit(self) -> None:
        classifier = self._classifier(np.array([[0.1, 4.0]], dtype=np.float32))

        prediction = classifier.classify(_frame())

        assert prediction.state is ShedState.SHEDDING
        assert prediction.confidence > 0.9

    def test_returns_a_full_distribution(self) -> None:
        classifier = self._classifier(np.array([[1.0, 1.0]], dtype=np.float32))

        prediction = classifier.classify(_frame())

        assert set(prediction.probabilities) == {"normal", "shedding"}
        assert sum(prediction.probabilities.values()) == pytest.approx(1.0, abs=1e-5)

    def test_handles_three_labels(self) -> None:
        classifier = self._classifier(
            np.array([[0.0, 3.0, 0.5]], dtype=np.float32),
            labels=("normal", "opaque", "shedding"),
        )

        prediction = classifier.classify(_frame())

        assert prediction.state is ShedState.OPAQUE

    def test_rejects_a_dimension_mismatch(self) -> None:
        classifier = self._classifier(np.array([[0.0, 1.0, 2.0]], dtype=np.float32))

        with pytest.raises(Exception, match="不一致"):
            classifier.classify(_frame())

    def test_rejects_empty_output(self) -> None:
        classifier = OnnxStateClassifier(
            session=_FakeSession(None),
            input_name="input",
            name="onnx:test",
            labels=("normal",),
        )

        with pytest.raises(Exception, match="没有输出"):
            classifier.classify(_frame())

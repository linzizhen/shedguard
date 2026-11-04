"""基于 ONNX 的蜕皮状态分类器。

模型由 `ml/train_state_classifier.py` 导出，输入是已裁剪并缩放到 `input_size × input_size`
的 RGB 图，输出是各状态的 logits。

类别顺序不硬编码在服务端，而是从同名 `.labels.json` 读取 —— 这样二态模型与三态模型可以
共存，换模型文件即可，代码不动。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState, StatePrediction, softmax
from shedguard_server.errors import ModelUnavailableError, StorageUnavailableError

DEFAULT_INPUT_SIZE: Final = 224
CHANNEL_COUNT: Final = 3
IMAGENET_MEAN: Final = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD: Final = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def labels_path_for(model_path: Path) -> Path:
    """与模型同名的标签文件：`gecko-state.onnx` → `gecko-state.labels.json`。"""
    return model_path.with_suffix(".labels.json")


@dataclass(frozen=True, slots=True)
class OnnxStateClassifier:
    """把 ONNX 模型包装成 `StateClassifier`。"""

    session: Any
    input_name: str
    name: str
    labels: tuple[str, ...]
    input_size: int = DEFAULT_INPUT_SIZE

    @classmethod
    def from_path(
        cls, model_path: Path, labels_path: Path | None = None
    ) -> OnnxStateClassifier:
        if not model_path.is_file():
            raise StorageUnavailableError(f"分类模型不存在: {model_path.name}")

        labels, input_size = load_labels(labels_path or labels_path_for(model_path))

        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - 依赖缺失时的兜底
            raise StorageUnavailableError("缺少 onnxruntime，无法加载分类模型") from exc

        try:
            session = ort.InferenceSession(
                model_path.as_posix(), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise StorageUnavailableError(f"分类模型加载失败: {model_path.name}") from exc

        inputs = session.get_inputs()
        if not inputs:
            raise StorageUnavailableError("分类模型没有输入节点")
        return cls(
            session=session,
            input_name=str(inputs[0].name),
            name=f"onnx:{model_path.stem}",
            labels=labels,
            input_size=input_size,
        )

    def classify(self, frame: ImageFrame) -> StatePrediction:
        resized = cv2.resize(
            frame.rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_LINEAR
        )
        tensor = resized.astype(np.float32) / 255.0
        tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD
        batch = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...].astype(np.float32)

        outputs = self.session.run(None, {self.input_name: batch})
        if not outputs or outputs[0] is None:
            raise ModelUnavailableError("分类模型没有输出")

        logits = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        if logits.size != len(self.labels):
            raise ModelUnavailableError(
                f"分类模型输出维度 {logits.size} 与标签数 {len(self.labels)} 不一致"
            )

        probabilities = softmax(logits)
        index = int(np.argmax(probabilities))
        return StatePrediction(
            state=ShedState(self.labels[index]),
            confidence=float(probabilities[index]),
            probabilities={
                label: float(probabilities[position])
                for position, label in enumerate(self.labels)
            },
        )


def load_labels(path: Path) -> tuple[tuple[str, ...], int]:
    """读取类别顺序与输入尺寸；标签必须都是合法的非 unknown 状态。"""
    if not path.is_file():
        raise StorageUnavailableError(f"分类标签不存在: {path.name}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageUnavailableError(f"分类标签无法解析: {path.name}") from exc

    if isinstance(raw, dict):
        raw_labels = raw.get("labels")
        input_size = int(raw.get("input_size", DEFAULT_INPUT_SIZE))
    else:
        raw_labels = raw
        input_size = DEFAULT_INPUT_SIZE

    if not isinstance(raw_labels, list) or not raw_labels:
        raise StorageUnavailableError(f"分类标签格式不对: {path.name}")

    labels: list[str] = []
    for item in raw_labels:
        label = str(item)
        try:
            state = ShedState(label)
        except ValueError as exc:
            raise StorageUnavailableError(f"未知的蜕皮状态标签: {label!r}") from exc
        if state is ShedState.UNKNOWN:
            raise StorageUnavailableError("分类标签不能是 unknown，它由服务层判定")
        labels.append(label)

    return tuple(labels), input_size

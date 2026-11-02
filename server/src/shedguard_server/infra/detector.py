"""基于 ONNX 的守宫检测器。

模型是 ultralytics 导出的 YOLOv8n 单类别检测。输出形如 `(1, 5, 8400)`，
四个坐标是相对 640 输入的 cx、cy、w、h，第五行是置信度。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from shedguard_server.domain.detection import Detection
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.errors import StorageUnavailableError

INPUT_SIZE = 640
CHANNEL_COUNT = 3
COORDINATE_COUNT = 4
PADDING_VALUE = 114


@dataclass(frozen=True, slots=True)
class OnnxDetector:
    """把 ONNX 模型包装成 `Detector`。

    只在真正推理时才触碰 onnxruntime，构造失败会抛出 `StorageUnavailableError`，
    让 `/readyz` 能反映「模型文件坏了」。
    """

    session: Any
    input_name: str
    name: str
    min_confidence: float = 0.35

    @classmethod
    def from_path(cls, model_path: Path, *, min_confidence: float = 0.35) -> OnnxDetector:
        if not model_path.is_file():
            raise StorageUnavailableError(f"检测模型不存在: {model_path.name}")
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - 依赖缺失时的兜底
            raise StorageUnavailableError("缺少 onnxruntime，无法加载检测模型") from exc

        try:
            session = ort.InferenceSession(
                model_path.as_posix(), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise StorageUnavailableError(f"检测模型加载失败: {model_path.name}") from exc

        inputs = session.get_inputs()
        if not inputs:
            raise StorageUnavailableError("检测模型没有输入节点")
        return cls(
            session=session,
            input_name=str(inputs[0].name),
            name=f"onnx:{model_path.stem}",
            min_confidence=min_confidence,
        )

    def detect(self, frame: ImageFrame) -> Detection | None:
        canvas, scale, pad_x, pad_y = _letterbox(frame)
        tensor = canvas.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]
        outputs = self.session.run(None, {self.input_name: tensor})
        if not outputs:
            return None

        predictions = np.asarray(outputs[0])
        if predictions.ndim == 3:
            predictions = predictions[0]
        if predictions.shape[0] <= predictions.shape[1]:
            predictions = predictions.T
        if predictions.shape[1] < COORDINATE_COUNT + 1:
            return None

        scores = predictions[:, COORDINATE_COUNT]
        best = int(np.argmax(scores))
        confidence = float(scores[best])
        if confidence < self.min_confidence:
            return None

        center_x, center_y, box_width, box_height = (
            float(value) for value in predictions[best, :COORDINATE_COUNT]
        )
        x1 = (center_x - box_width / 2 - pad_x) / scale
        y1 = (center_y - box_height / 2 - pad_y) / scale
        x2 = (center_x + box_width / 2 - pad_x) / scale
        y2 = (center_y + box_height / 2 - pad_y) / scale

        return Detection(
            x1=max(0, min(round(x1), frame.width - 1)),
            y1=max(0, min(round(y1), frame.height - 1)),
            x2=max(1, min(round(x2), frame.width)),
            y2=max(1, min(round(y2), frame.height)),
            confidence=confidence,
        )


def _letterbox(frame: ImageFrame) -> tuple[NDArray[np.uint8], float, int, int]:
    """等比缩放并居中填充到 640×640，同时返回缩放系数与左上留白。"""
    scale = min(INPUT_SIZE / frame.width, INPUT_SIZE / frame.height)
    new_width = max(1, round(frame.width * scale))
    new_height = max(1, round(frame.height * scale))
    resized = cv2.resize(frame.rgb, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((INPUT_SIZE, INPUT_SIZE, CHANNEL_COUNT), PADDING_VALUE, dtype=np.uint8)
    pad_x = (INPUT_SIZE - new_width) // 2
    pad_y = (INPUT_SIZE - new_height) // 2
    canvas[pad_y : pad_y + new_height, pad_x : pad_x + new_width] = resized
    return canvas, scale, pad_x, pad_y
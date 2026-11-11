"""复核第一步：把 `data/collected/` 的网络图片跑一遍检测器裁剪 + 自动打标 + 去重指纹。

产物（全部在 gitignore 里，只在本地）：
- `data/collected_crops/<source>/<name>`：守宫本体裁剪图（未检出时退回整图）
- `data/collected_crops/manifest.csv`：一张图一行，含检测框、检测置信度、模型自动状态、
  dHash（8x8 差分感知哈希，用于近重复聚类）。

人工复核是在裁剪图上做的，因为最终训练/推理都吃裁剪图，看原图会误判。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import crop_box, crop_frame
from shedguard_server.infra.classifier import OnnxStateClassifier
from shedguard_server.infra.detector import OnnxDetector

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "data" / "collected"
CROP_ROOT = PROJECT_ROOT / "data" / "collected_crops"
DETECTOR_PATH = PROJECT_ROOT / "ml" / "models" / "gecko-det.onnx"
CLASSIFIER_PATH = PROJECT_ROOT / "ml" / "models" / "gecko-state.onnx"
MANIFEST = CROP_ROOT / "manifest.csv"
CROP_PADDING = 0.08
MIN_CONFIDENCE = 0.35
JPEG_QUALITY = 95
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def load_frame(path: Path) -> ImageFrame:
    data = np.fromfile(str(path), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"无法解码图片: {path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return ImageFrame(width=int(rgb.shape[1]), height=int(rgb.shape[0]), rgb=rgb)


def save_crop(frame: ImageFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:  # pragma: no cover
        raise RuntimeError(f"编码失败: {path}")
    buf.tofile(str(path))


def dhash(frame: ImageFrame, size: int = 8) -> str:
    """差分感知哈希：缩到 (size+1)×size 灰度，比较相邻像素，得 size*size 位。"""
    gray = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    bits = 0
    for value in diff.flatten():
        bits = (bits << 1) | int(bool(value))
    return f"{bits:0{size * size // 4}x}"


def main() -> int:
    if not SOURCE_ROOT.is_dir():
        print(f"找不到源目录: {SOURCE_ROOT}", file=sys.stderr)
        return 1
    detector = OnnxDetector.from_path(DETECTOR_PATH, min_confidence=MIN_CONFIDENCE)
    classifier = OnnxStateClassifier.from_path(CLASSIFIER_PATH)

    rows: list[dict[str, object]] = []
    stats = {"total": 0, "detected": 0, "undetected": 0, "decode_error": 0}
    for source_dir in sorted(p for p in SOURCE_ROOT.iterdir() if p.is_dir()):
        source = source_dir.name
        for path in sorted(source_dir.iterdir()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            stats["total"] += 1
            try:
                frame = load_frame(path)
            except ValueError:
                stats["decode_error"] += 1
                rows.append(
                    {
                        "source": source,
                        "name": path.name,
                        "crop_rel": "",
                        "width": "",
                        "height": "",
                        "detected": 0,
                        "det_conf": "",
                        "box": "",
                        "auto_state": "decode_error",
                        "auto_conf": "",
                        "p_normal": "",
                        "p_shedding": "",
                        "dhash": "",
                    }
                )
                continue

            detection = detector.detect(frame)
            if detection is None:
                stats["undetected"] += 1
                crop = frame
                box_text = ""
                det_conf: object = ""
                detected = 0
            else:
                stats["detected"] += 1
                x1, y1, x2, y2 = crop_box(
                    (detection.x1, detection.y1, detection.x2, detection.y2),
                    width=frame.width,
                    height=frame.height,
                    padding=CROP_PADDING,
                )
                crop = crop_frame(frame, (x1, y1, x2, y2))
                box_text = f"{x1},{y1},{x2},{y2}"
                det_conf = round(detection.confidence, 4)
                detected = 1

            crop_rel = Path(source) / (path.stem + ".jpg")
            save_crop(crop, CROP_ROOT / crop_rel)

            try:
                prediction = classifier.classify(crop)
                auto_state = str(prediction.state)
                auto_conf = round(prediction.confidence, 4)
                p_normal = round(prediction.probabilities.get("normal", 0.0), 4)
                p_shedding = round(prediction.probabilities.get("shedding", 0.0), 4)
            except Exception as exc:  # pragma: no cover - 分类失败不应中断整批
                auto_state = f"error:{type(exc).__name__}"
                auto_conf = p_normal = p_shedding = ""

            rows.append(
                {
                    "source": source,
                    "name": path.name,
                    "crop_rel": crop_rel.as_posix(),
                    "width": crop.width,
                    "height": crop.height,
                    "detected": detected,
                    "det_conf": det_conf,
                    "box": box_text,
                    "auto_state": auto_state,
                    "auto_conf": auto_conf,
                    "p_normal": p_normal,
                    "p_shedding": p_shedding,
                    "dhash": dhash(crop),
                }
            )

    CROP_ROOT.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "name",
        "crop_rel",
        "width",
        "height",
        "detected",
        "det_conf",
        "box",
        "auto_state",
        "auto_conf",
        "p_normal",
        "p_shedding",
        "dhash",
    ]
    with MANIFEST.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(
        "处理完成: total={total} detected={detected} undetected={undetected} "
        "decode_error={decode_error}".format(**stats)
    )
    print(f"清单: {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

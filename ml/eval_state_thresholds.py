"""对比 v2/v3 两个状态分类器在不同判定阈值下的表现。

用途：A/B 只给了 argmax 的单一工作点，但产品真正要定的是「p(shedding) 超过多少才提醒」。
这里按阈值扫一遍，输出准确率 / 蜕皮召回 / 蜕皮精确率，供选模型与定阈值。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server" / "src"))

from shedguard_server.domain.imaging import ImageFrame  # noqa: E402
from shedguard_server.infra.classifier import OnnxStateClassifier  # noqa: E402

MODELS = {
    "v2": PROJECT_ROOT / "ml" / "models" / "gecko-state-v2.onnx",
    "v3": PROJECT_ROOT / "ml" / "models" / "gecko-state-v3.onnx",
}
SPLITS = {
    "valid": PROJECT_ROOT / "ml" / "datasets" / "gecko-state-v3" / "valid",
    "test": PROJECT_ROOT / "ml" / "datasets" / "gecko-state-v3" / "test",
}
THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def load_frame(path: Path) -> ImageFrame:
    bgr = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return ImageFrame(rgb=np.ascontiguousarray(rgb), width=rgb.shape[1], height=rgb.shape[0])


def collect(split_dir: Path) -> list[tuple[Path, int]]:
    items: list[tuple[Path, int]] = []
    for label, index in (("normal", 0), ("shedding", 1)):
        for path in sorted((split_dir / label).iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                items.append((path, index))
    return items


def sweep(model_path: Path, items: list[tuple[Path, int]]) -> dict[str, list[dict[str, float]]]:
    classifier = OnnxStateClassifier.from_path(model_path)
    scores: list[tuple[float, int]] = []
    for path, truth in items:
        prediction = classifier.classify(load_frame(path))
        positive = sum(v for k, v in prediction.probabilities.items() if k == "shedding")
        scores.append((positive, truth))

    rows: list[dict[str, float]] = []
    for threshold in THRESHOLDS:
        tp = fp = fn = tn = 0
        for probability, truth in scores:
            predicted = 1 if probability >= threshold else 0
            if truth == 1 and predicted == 1:
                tp += 1
            elif truth == 1:
                fn += 1
            elif predicted == 1:
                fp += 1
            else:
                tn += 1
        recall = tp / (tp + fn) if tp + fn else 0.0
        precision = tp / (tp + fp) if tp + fp else 0.0
        accuracy = (tp + tn) / len(scores)
        rows.append(
            {
                "threshold": threshold,
                "accuracy": round(accuracy, 4),
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            }
        )
    return {"rows": rows}


def main() -> int:
    report: dict[str, dict[str, dict[str, list[dict[str, float]]]]] = {}
    for name, model_path in MODELS.items():
        report[name] = {}
        for split, split_dir in SPLITS.items():
            items = collect(split_dir)
            report[name][split] = sweep(model_path, items)
            print(f"[{name}/{split}] n={len(items)}")
            for row in report[name][split]["rows"]:
                print(
                    f"  T={row['threshold']:.2f}  acc={row['accuracy']:.4f} "
                    f"recall={row['recall']:.4f} precision={row['precision']:.4f} "
                    f"(tp={row['tp']} fp={row['fp']} fn={row['fn']} tn={row['tn']})"
                )
    target = PROJECT_ROOT / "ml" / "runs" / "threshold-swap-v2v3.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
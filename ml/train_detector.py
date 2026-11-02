"""训练守宫单类别检测器，并导出服务端可直接加载的 ONNX。

输入是 `prepare_detection_dataset.py` 产出的数据集，输出是：
- `ml/runs/<name>/weights/best.pt`：训练权重
- `ml/models/<name>.onnx`：给 `SHEDGUARD_DETECTOR_MODEL` 用
- `ml/runs/<name>/summary.json`：测试集指标与训练参数，便于复现
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_YAML = PROJECT_ROOT / "ml" / "datasets" / "gecko-det" / "dataset.yaml"
RUNS_DIR = PROJECT_ROOT / "ml" / "runs"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
BASE_WEIGHTS = "yolov8n.pt"
SEED = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练守宫检测器")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--name", default="gecko-det")
    parser.add_argument(
        "--device", default="", help="留空自动选择；也可显式指定 cpu / 0"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not DATASET_YAML.is_file():
        raise SystemExit(f"数据集不存在: {DATASET_YAML}，先跑 ml/prepare_detection_dataset.py")

    model = YOLO(BASE_WEIGHTS)
    model.train(
        data=str(DATASET_YAML),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device or None,
        project=str(RUNS_DIR),
        name=args.name,
        exist_ok=True,
        seed=SEED,
        patience=20,
        workers=4,
        verbose=True,
    )

    best = RUNS_DIR / args.name / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit(f"训练未产出权重: {best}")

    trained = YOLO(str(best))
    exported = Path(trained.export(format="onnx", imgsz=args.imgsz, opset=17, simplify=False))
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / f"{args.name}.onnx"
    shutil.copy2(exported, target)

    metrics = trained.val(
        data=str(DATASET_YAML),
        split="test",
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(RUNS_DIR),
        name=f"{args.name}-val",
        exist_ok=True,
    )
    box = metrics.box
    summary = {
        "name": args.name,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": args.device or "auto",
        "seed": SEED,
        "weights": best.as_posix(),
        "onnx": target.as_posix(),
        "test": {
            "precision": round(float(box.mp), 4),
            "recall": round(float(box.mr), 4),
            "map50": round(float(box.map50), 4),
            "map50_95": round(float(box.map), 4),
        },
    }
    summary_path = RUNS_DIR / args.name / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
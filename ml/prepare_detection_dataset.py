"""把 gecko_1 的分割标注转成检测框，构建 YOLO 检测数据集。

只保留 `gecko` 类（索引 0）：蜕皮与异常是状态标签，不是物体标签，
它们不能作为检测目标，否则模型会去学「哪里像蜕皮」而不是「守宫在哪」。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

SOURCE_ROOT = Path("data/raw/gecko1")
TARGET_ROOT = Path("ml/datasets/gecko-det")
SPLITS = ("train", "valid", "test")
GECKO_CLASS = 0
MIN_AREA_RATIO = 0.01
MIN_SIDE_PX = 24


@dataclass
class SplitStats:
    split: str
    images_kept: int = 0
    boxes_kept: int = 0
    images_dropped_no_box: int = 0
    boxes_dropped_small: int = 0
    area_ratios: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        ratios = sorted(self.area_ratios)
        return {
            "split": self.split,
            "images_kept": self.images_kept,
            "boxes_kept": self.boxes_kept,
            "images_dropped_no_box": self.images_dropped_no_box,
            "boxes_dropped_small": self.boxes_dropped_small,
            "area_ratio_min": round(ratios[0], 4) if ratios else None,
            "area_ratio_median": round(ratios[len(ratios) // 2], 4) if ratios else None,
            "area_ratio_max": round(ratios[-1], 4) if ratios else None,
        }


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as handle:
        width, height = handle.size
    return int(width), int(height)


def parse_label_line(line: str) -> tuple[int, list[tuple[float, float]]] | None:
    parts = line.split()
    if len(parts) < 7:
        return None
    class_id = int(parts[0])
    coords = [float(value) for value in parts[1:]]
    points = [(coords[index], coords[index + 1]) for index in range(0, len(coords) - 1, 2)]
    return class_id, points


def polygon_to_box(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return (
        (x_min + x_max) / 2,
        (y_min + y_max) / 2,
        x_max - x_min,
        y_max - y_min,
    )


def convert_split(split: str) -> SplitStats:
    stats = SplitStats(split=split)
    image_dir = SOURCE_ROOT / split / "images"
    label_dir = SOURCE_ROOT / split / "labels"
    target_images = TARGET_ROOT / split / "images"
    target_labels = TARGET_ROOT / split / "labels"
    target_images.mkdir(parents=True, exist_ok=True)
    target_labels.mkdir(parents=True, exist_ok=True)

    for image_path in sorted(image_dir.glob("*.jpg")):
        width, height = image_size(image_path)
        label_path = label_dir / f"{image_path.stem}.txt"
        kept_lines: list[str] = []
        if label_path.is_file():
            for raw_line in label_path.read_text(encoding="utf-8").splitlines():
                parsed = parse_label_line(raw_line.strip())
                if parsed is None:
                    continue
                class_id, points = parsed
                if class_id != GECKO_CLASS:
                    continue
                center_x, center_y, box_width, box_height = polygon_to_box(points)
                area_ratio = box_width * box_height
                short_side = min(box_width * width, box_height * height)
                if area_ratio < MIN_AREA_RATIO or short_side < MIN_SIDE_PX:
                    stats.boxes_dropped_small += 1
                    continue
                kept_lines.append(
                    f"{GECKO_CLASS} {center_x:.6f} {center_y:.6f} {box_width:.6f} {box_height:.6f}"
                )
                stats.area_ratios.append(area_ratio)

        if not kept_lines:
            stats.images_dropped_no_box += 1
            continue

        shutil.copy2(image_path, target_images / image_path.name)
        (target_labels / f"{image_path.stem}.txt").write_text(
            "\n".join(kept_lines) + "\n", encoding="utf-8"
        )
        stats.images_kept += 1
        stats.boxes_kept += len(kept_lines)

    return stats


def dataset_hash() -> str:
    digest = hashlib.sha256()
    for split in SPLITS:
        label_dir = TARGET_ROOT / split / "labels"
        for label_path in sorted(label_dir.glob("*.txt")):
            digest.update(f"{split}/{label_path.name}".encode())
            digest.update(label_path.read_bytes())
    return digest.hexdigest()


def write_dataset_yaml() -> None:
    root = TARGET_ROOT.resolve().as_posix()
    content = (
        f"path: {root}\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "names:\n"
        "  0: gecko\n"
    )
    (TARGET_ROOT / "dataset.yaml").write_text(content, encoding="utf-8")


def main() -> None:
    if TARGET_ROOT.exists():
        shutil.rmtree(TARGET_ROOT)
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    stats = [convert_split(split) for split in SPLITS]
    write_dataset_yaml()

    report = {
        "source": SOURCE_ROOT.as_posix(),
        "target": TARGET_ROOT.as_posix(),
        "dataset_hash": dataset_hash(),
        "splits": [item.as_dict() for item in stats],
        "totals": {
            "images": sum(item.images_kept for item in stats),
            "boxes": sum(item.boxes_kept for item in stats),
            "images_dropped": sum(item.images_dropped_no_box for item in stats),
            "boxes_dropped": sum(item.boxes_dropped_small for item in stats),
        },
    }
    (TARGET_ROOT / "stats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
"""把 gecko_1 的检测标注转成「守宫本体裁剪图 + 蜕皮状态标签」分类数据集。

为什么不在检测器里加状态类别：检测标注里「本体框」与「蜕皮框」是两个重叠的框，
重组语义成本高，而且状态定义会反复调整。把状态交给独立的分类器，检测器半年不用动。

标签规则（与 `docs/specs/2026-11-04-shedding-state-design.md` 一致）：
- 图里有 `gecko` 框、没有 `gecko-shedding` 框 → `normal`
- 图里同时有两者 → `shedding`
- 只有 `gecko-shedding` 框 → 丢弃（定位不到本体，无法裁剪）

蒙白（`opaque`）类当前没有任何数据来源，所以本脚本只会产出二态数据集；
将来有了标注，把图片放进 `<split>/opaque/` 再跑一次即可，类别顺序由 `labels.json` 决定。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from prepare_detection_dataset import image_size, parse_label_line, polygon_to_box

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_ROOT = PROJECT_ROOT / "data" / "raw" / "gecko1"
TARGET_ROOT = PROJECT_ROOT / "ml" / "datasets" / "gecko-state"
SPLITS = ("train", "valid", "test")

GECKO_CLASS = 0
SHEDDING_CLASS = 2
CLASS_ORDER = ("normal", "opaque", "shedding")
CROP_PADDING = 0.08
MIN_SIDE_PX = 24
JPEG_QUALITY = 95
INPUT_SIZE = 224


@dataclass
class SplitStats:
    split: str
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASS_ORDER, 0))
    dropped_no_gecko_box: int = 0
    dropped_too_small: int = 0
    side_lengths: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        sides = sorted(self.side_lengths)
        return {
            "split": self.split,
            "counts": {name: count for name, count in self.counts.items() if count},
            "dropped_no_gecko_box": self.dropped_no_gecko_box,
            "dropped_too_small": self.dropped_too_small,
            "side_min": sides[0] if sides else None,
            "side_median": sides[len(sides) // 2] if sides else None,
            "side_max": sides[-1] if sides else None,
        }


def read_boxes(label_path: Path) -> list[tuple[int, tuple[float, float, float, float]]]:
    """读出每行标注的类别与归一化框（多边形转外接框）。"""
    boxes: list[tuple[int, tuple[float, float, float, float]]] = []
    if not label_path.is_file():
        return boxes
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_label_line(raw_line.strip())
        if parsed is None:
            continue
        class_id, points = parsed
        boxes.append((class_id, polygon_to_box(points)))
    return boxes


def pixel_crop(
    box: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
    padding: float,
) -> tuple[int, int, int, int]:
    """把归一化框换算成像素并外扩，夹紧到图像范围内。"""
    center_x, center_y, box_width, box_height = box
    x1 = (center_x - box_width / 2) * width
    x2 = (center_x + box_width / 2) * width
    y1 = (center_y - box_height / 2) * height
    y2 = (center_y + box_height / 2) * height

    pad_x = (x2 - x1) * padding
    pad_y = (y2 - y1) * padding

    left = max(int(round(x1 - pad_x)), 0)
    top = max(int(round(y1 - pad_y)), 0)
    right = min(int(round(x2 + pad_x)), width)
    bottom = min(int(round(y2 + pad_y)), height)
    return left, top, right, bottom


def class_of(class_ids: Iterable[int]) -> str:
    """只要出现过蜕皮标注就算 shedding —— 漏报一次蜕皮的代价更高。"""
    return "shedding" if SHEDDING_CLASS in set(class_ids) else "normal"


def convert_split(split: str) -> SplitStats:
    stats = SplitStats(split=split)
    image_dir = SOURCE_ROOT / split / "images"
    label_dir = SOURCE_ROOT / split / "labels"

    for image_path in sorted(image_dir.glob("*.jpg")):
        boxes = read_boxes(label_dir / f"{image_path.stem}.txt")
        gecko_boxes = [box for class_id, box in boxes if class_id == GECKO_CLASS]
        if not gecko_boxes:
            stats.dropped_no_gecko_box += 1
            continue

        # 一张图里可能有多个个体，取面积最大的那个 —— 分类器只看一个主体。
        largest = max(gecko_boxes, key=lambda box: box[2] * box[3])
        width, height = image_size(image_path)
        crop = pixel_crop(largest, width=width, height=height, padding=CROP_PADDING)
        left, top, right, bottom = crop
        if min(right - left, bottom - top) < MIN_SIDE_PX:
            stats.dropped_too_small += 1
            continue

        label = class_of(class_id for class_id, _ in boxes)
        target_dir = TARGET_ROOT / split / label
        target_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(image_path) as handle:
            cropped = handle.convert("RGB").crop(crop)
            cropped.save(target_dir / f"{image_path.stem}.jpg", quality=JPEG_QUALITY)

        stats.counts[label] += 1
        stats.side_lengths.append(min(right - left, bottom - top))

    return stats


def dataset_hash() -> str:
    digest = hashlib.sha256()
    for split in SPLITS:
        for class_dir in sorted((TARGET_ROOT / split).glob("*")):
            if not class_dir.is_dir():
                continue
            for image_path in sorted(class_dir.glob("*.jpg")):
                digest.update(f"{split}/{class_dir.name}/{image_path.name}".encode())
                digest.update(image_path.read_bytes())
    return digest.hexdigest()


def present_classes(stats: list[SplitStats]) -> tuple[str, ...]:
    """只输出实际有数据的类别，顺序固定，避免标签顺序随目录名变化。"""
    seen = {name for item in stats for name, count in item.counts.items() if count}
    return tuple(name for name in CLASS_ORDER if name in seen)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建蜕皮状态分类数据集")
    parser.parse_args()

    if not SOURCE_ROOT.is_dir():
        raise SystemExit(f"原始数据集不存在: {SOURCE_ROOT}")
    if TARGET_ROOT.exists():
        shutil.rmtree(TARGET_ROOT)
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    stats = [convert_split(split) for split in SPLITS]
    labels = present_classes(stats)

    (TARGET_ROOT / "labels.json").write_text(
        json.dumps({"labels": list(labels), "input_size": INPUT_SIZE}, indent=2),
        encoding="utf-8",
    )

    report = {
        "source": SOURCE_ROOT.as_posix(),
        "target": TARGET_ROOT.as_posix(),
        "labels": list(labels),
        "input_size": INPUT_SIZE,
        "crop_padding": CROP_PADDING,
        "dataset_hash": dataset_hash(),
        "splits": [item.as_dict() for item in stats],
        "totals": {
            name: sum(item.counts[name] for item in stats) for name in labels
        },
    }
    (TARGET_ROOT / "stats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

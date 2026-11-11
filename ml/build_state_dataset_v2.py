"""把人工复核通过的网络图片并入分类数据集，产出 `gecko-state-v2`。

设计要点（为了 A/B 可比较）：
- **测试集完全不动**：v2 的 train/valid/test 三份原始 gecko1 数据原样复制；人工复核通过的
  新图**只加到 train**，valid/test 保持原样，这样 v1 与 v2 在同一把尺子上量。
- **与原始数据交叉查重**：新图 dHash 与现有全部图片（含 test）比对，汉明距离 <= 阈值即跳过，
  防止「训练集里塞一张测试集的近重复图」造成虚高。
- 新图文件名加 `web_<cluster>_` 前缀，便于追溯来源。
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CROP_ROOT = PROJECT_ROOT / "data" / "collected_crops"
REVIEW = CROP_ROOT / "review.csv"
EXISTING = PROJECT_ROOT / "ml" / "datasets" / "gecko-state"
TARGET = PROJECT_ROOT / "ml" / "datasets" / "gecko-state-v2"
SPLITS = ("train", "valid", "test")
CLASS_ORDER = ("normal", "shedding")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
MIN_SIDE_PX = 64
CROSS_DUP_THRESHOLD = 6


def load_bgr(path: Path) -> "np.ndarray | None":
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def dhash_bgr(bgr: "np.ndarray", size: int = 8) -> str:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    bits = 0
    for value in diff.flatten():
        bits = (bits << 1) | int(bool(value))
    return f"{bits:0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for split in SPLITS:
        for label in CLASS_ORDER:
            (TARGET / split / label).mkdir(parents=True, exist_ok=True)

    # 1) 原样复制 gecko1 派生数据
    base_counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        base_counts[split] = {}
        for label in CLASS_ORDER:
            src_dir = EXISTING / split / label
            dst_dir = TARGET / split / label
            count = 0
            if src_dir.is_dir():
                for path in src_dir.iterdir():
                    if path.suffix.lower() in IMAGE_SUFFIXES:
                        shutil.copy2(path, dst_dir / path.name)
                        count += 1
            base_counts[split][label] = count

    # 2) 计算现有全部图片的 dHash 池，用于交叉查重
    existing_hashes: list[str] = []
    for split in SPLITS:
        for label in CLASS_ORDER:
            for path in (EXISTING / split / label).iterdir():
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                bgr = load_bgr(path)
                if bgr is not None:
                    existing_hashes.append(dhash_bgr(bgr))

    # 3) 把复核通过、且不与现有数据重复的新图加入 train
    added = {"normal": 0, "shedding": 0}
    skipped_dup = 0
    skipped_small = 0
    skipped_decode = 0
    with REVIEW.open(encoding="utf-8") as fh:
        review_rows = list(csv.DictReader(fh))
    for row in review_rows:
        if row["label"] not in CLASS_ORDER:
            continue
        crop_path = CROP_ROOT / row["repr_crop"]
        bgr = load_bgr(crop_path)
        if bgr is None:
            skipped_decode += 1
            continue
        if min(bgr.shape[0], bgr.shape[1]) < MIN_SIDE_PX:
            skipped_small += 1
            continue
        fingerprint = dhash_bgr(bgr)
        if any(hamming(fingerprint, other) <= CROSS_DUP_THRESHOLD for other in existing_hashes):
            skipped_dup += 1
            continue
        suffix = Path(row["repr_crop"]).suffix or ".jpg"
        name = f"web_{int(row['cluster_id']):03d}_{Path(row['repr_name']).stem}{suffix}"
        shutil.copy2(crop_path, TARGET / "train" / row["label"] / name)
        existing_hashes.append(fingerprint)
        added[row["label"]] += 1

    # 4) 统计与元数据
    final_counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        final_counts[split] = {}
        for label in CLASS_ORDER:
            final_counts[split][label] = sum(
                1
                for p in (TARGET / split / label).iterdir()
                if p.suffix.lower() in IMAGE_SUFFIXES
            )

    (TARGET / "labels.json").write_text(
        json.dumps({"labels": list(CLASS_ORDER), "input_size": 224}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stats = {
        "source": {
            "base": str(EXISTING).replace("\\", "/"),
            "collected": str(CROP_ROOT).replace("\\", "/"),
        },
        "labels": list(CLASS_ORDER),
        "input_size": 224,
        "base_counts": base_counts,
        "added_to_train": added,
        "skipped_duplicate": skipped_dup,
        "skipped_too_small": skipped_small,
        "skipped_decode_error": skipped_decode,
        "final_counts": final_counts,
        "cross_dup_threshold": CROSS_DUP_THRESHOLD,
    }
    digest = hashlib.sha256(
        json.dumps(final_counts, sort_keys=True).encode("utf-8")
    ).hexdigest()
    stats["dataset_hash"] = digest
    (TARGET / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"基础数据: {base_counts}")
    print(f"新增到 train: {added}")
    print(f"跳过: duplicate={skipped_dup} too_small={skipped_small} decode={skipped_decode}")
    print(f"最终: {final_counts}")
    print(f"dataset_hash={digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

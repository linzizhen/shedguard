"""把 Bing 收集的蜕皮图并入分类数据集，产出 `gecko-state-v3`。

与 v2 的区别：

- 基础集改为 `gecko-state-v2`（已含上一轮人工复核的 88 张）；
- 新图来自 `data/collected/bing_*`，**标签用模型置信度硬门控**而不是人工逐张判定：
  `p(shedding) >= 0.85` 记为 shedding、`<= 0.25` 记为 normal，中间灰区（0.25–0.85）
  一律丢掉。这样既不把模糊样本喂进训练，也不假装自己逐张看过 400 张图。

仍然坚持 v2 的两条纪律：**valid/test 完全不动**（保 A/B 可比），**新图与全部现有图
做 dHash 交叉查重**（防止训练集塞进测试集的近重复图）。
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
MANIFEST = CROP_ROOT / "manifest.csv"
EXISTING = PROJECT_ROOT / "ml" / "datasets" / "gecko-state-v2"
TARGET = PROJECT_ROOT / "ml" / "datasets" / "gecko-state-v3"
SPLITS = ("train", "valid", "test")
CLASS_ORDER = ("normal", "shedding")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
MIN_SIDE_PX = 64
CROSS_DUP_THRESHOLD = 6
POSITIVE_THRESHOLD = 0.85
NEGATIVE_THRESHOLD = 0.25


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


def label_of(row: dict[str, str]) -> str | None:
    """按模型概率给硬标签；灰区返回 None。"""
    raw = row.get("p_shedding") or ""
    if not raw:
        return None
    try:
        probability = float(raw)
    except ValueError:
        return None
    if probability >= POSITIVE_THRESHOLD:
        return "shedding"
    if probability <= NEGATIVE_THRESHOLD:
        return "normal"
    return None


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for split in SPLITS:
        for label in CLASS_ORDER:
            (TARGET / split / label).mkdir(parents=True, exist_ok=True)

    base_counts: dict[str, dict[str, int]] = {}
    existing_hashes: list[str] = []
    for split in SPLITS:
        base_counts[split] = {}
        for label in CLASS_ORDER:
            src_dir = EXISTING / split / label
            dst_dir = TARGET / split / label
            count = 0
            for path in sorted(src_dir.iterdir()):
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                shutil.copy2(path, dst_dir / path.name)
                count += 1
                bgr = load_bgr(path)
                if bgr is not None:
                    existing_hashes.append(dhash_bgr(bgr))
            base_counts[split][label] = count

    added = {"normal": 0, "shedding": 0}
    skipped = {"ambiguous": 0, "duplicate": 0, "too_small": 0, "decode_error": 0, "non_bing": 0}

    with MANIFEST.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        source = row["source"]
        if not source.startswith("bing_"):
            skipped["non_bing"] += 1
            continue
        label = label_of(row)
        if label is None:
            skipped["ambiguous"] += 1
            continue
        crop_path = CROP_ROOT / row["crop_rel"]
        bgr = load_bgr(crop_path)
        if bgr is None:
            skipped["decode_error"] += 1
            continue
        if min(int(bgr.shape[0]), int(bgr.shape[1])) < MIN_SIDE_PX:
            skipped["too_small"] += 1
            continue
        fingerprint = dhash_bgr(bgr)
        if any(hamming(fingerprint, other) <= CROSS_DUP_THRESHOLD for other in existing_hashes):
            skipped["duplicate"] += 1
            continue
        stem = Path(row["crop_rel"]).stem
        name = f"{source}_{stem}.jpg"
        shutil.copy2(crop_path, TARGET / "train" / label / name)
        existing_hashes.append(fingerprint)
        added[label] += 1

    final_counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        final_counts[split] = {}
        for label in CLASS_ORDER:
            final_counts[split][label] = sum(
                1 for p in (TARGET / split / label).iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
            )

    (TARGET / "labels.json").write_text(
        json.dumps({"labels": list(CLASS_ORDER), "input_size": 224}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stats = {
        "source": {
            "base": str(EXISTING).replace("\\", "/"),
            "manifest": str(MANIFEST).replace("\\", "/"),
        },
        "labels": list(CLASS_ORDER),
        "input_size": 224,
        "label_rule": {
            "shedding_threshold": POSITIVE_THRESHOLD,
            "normal_threshold": NEGATIVE_THRESHOLD,
        },
        "base_counts": base_counts,
        "added_to_train": added,
        "skipped": skipped,
        "final_counts": final_counts,
        "cross_dup_threshold": CROSS_DUP_THRESHOLD,
    }
    digest = hashlib.sha256(json.dumps(final_counts, sort_keys=True).encode("utf-8")).hexdigest()
    stats["dataset_hash"] = digest
    (TARGET / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"基础数据: {base_counts}")
    print(f"新增到 train: {added}")
    print(f"跳过: {skipped}")
    print(f"最终: {final_counts}")
    print(f"dataset_hash={digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
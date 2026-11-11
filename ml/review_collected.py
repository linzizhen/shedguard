"""人工复核结论（第一次逐张过完 325 个近重复簇后写下的判定）。

判定标准（保守，宁可少留）：
- 必须是豹纹守宫（Eublepharis macularius）；睫角、肥尾、睑虎、守宫科野生种一律 discard。
- 必须是能看清躯干的裁剪图；只有皮屑、脸部特写、远景小目标、空箱/空手一律 discard。
- 全身均匀奶白/灰白无法区分「白化/暴雪基因」与「蒙白」的一律 discard（不硬凑 opaque 类）。
- 有大幅卡通/字幕贴纸遮挡主体的一律 discard。
- `normal` = 无可见皮屑、花纹自然的健康个体；`shedding` = 身上可见白色/粉色蜕皮。

只把可信的图并进训练集，测试集保持原始 gecko1 不动，这样 A/B 对比才公平。
"""

from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CROP_ROOT = PROJECT_ROOT / "data" / "collected_crops"
DEDUP = CROP_ROOT / "dedup.csv"
REVIEW = CROP_ROOT / "review.csv"

NORMAL = [
    28, 30, 31, 32, 34, 35, 36, 39, 40, 59, 60, 64, 136, 139,
    140, 141, 142, 143, 144, 145, 146, 148, 149, 150, 152, 153, 154, 155, 156, 158, 159,
    175, 176, 177, 178, 179, 181, 182, 183, 185, 186, 187, 188, 189, 192, 193, 197, 198, 199,
    201, 203, 208, 224, 230, 243, 253, 255, 256, 259, 260, 263, 264, 267, 268, 282, 283, 288, 310,
]

SHEDDING = [0, 1, 2, 3, 4, 5, 6, 14, 61, 62, 63, 67, 68, 73, 75, 76, 78, 138, 190, 318]

# 备注：这些是复核中判为「疑似白化/暴雪、无法确认是否蒙白」而丢弃的簇，留档备查
WHITE_UNCERTAIN = [
    7, 9, 11, 12, 13, 15, 16, 20, 21, 22, 23, 24, 25, 26, 27, 44, 45, 46, 47, 48, 49,
    65, 66, 74, 81, 83, 84, 85, 86, 87, 88, 89, 90, 93, 94, 120, 121, 134, 195, 200, 204,
    214, 271, 285, 291,
]


def main() -> int:
    with DEDUP.open(encoding="utf-8") as fh:
        clusters = {int(row["cluster_id"]): row for row in csv.DictReader(fh)}

    label_by_id: dict[int, tuple[str, str]] = {}
    for cid in NORMAL:
        label_by_id[cid] = ("normal", "keep")
    for cid in SHEDDING:
        label_by_id[cid] = ("shedding", "keep")
    for cid in WHITE_UNCERTAIN:
        label_by_id.setdefault(cid, ("discard", "white_uncertain"))

    rows = []
    for cid in sorted(clusters):
        row = clusters[cid]
        label, reason = label_by_id.get(cid, ("discard", "other_species_or_low_quality"))
        rows.append(
            {
                "cluster_id": cid,
                "source": row["source"],
                "repr_name": row["repr_name"],
                "repr_crop": row["repr_crop"],
                "member_count": row["member_count"],
                "auto_votes": row["auto_votes"],
                "label": label,
                "reason": reason,
            }
        )

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    keep_normal = sum(1 for r in rows if r["label"] == "normal")
    keep_shedding = sum(1 for r in rows if r["label"] == "shedding")
    discard = sum(1 for r in rows if r["label"] == "discard")
    print(f"总簇 {len(rows)}：normal {keep_normal}，shedding {keep_shedding}，discard {discard}")
    print(f"清单: {REVIEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

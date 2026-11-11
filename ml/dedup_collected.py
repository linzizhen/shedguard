"""复核第二步：近重复聚类 + 生成 contact sheet（拼图）供人工逐张核对。

- 按 dHash 汉明距离聚类（同来源内，阈值默认 8 位/64），同一视频的连拍帧会并成一簇。
- 每簇取一张代表图，写 `data/collected_crops/dedup.csv`（cluster_id、代表图、成员数、自动票型）。
- 生成拼图 `data/collected_crops/sheets/sheet_XX.jpg`，每个缩略图左上角标序号（= cluster_id），
  便于人工按序号写标签。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CROP_ROOT = PROJECT_ROOT / "data" / "collected_crops"
MANIFEST = CROP_ROOT / "manifest.csv"
DEDUP = CROP_ROOT / "dedup.csv"
SHEET_DIR = CROP_ROOT / "sheets"
HAMMING_THRESHOLD = 8
COLS = 5
ROWS = 4
THUMB = 220
PAD = 6


def hamming(a: str, b: str) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def main() -> int:
    with MANIFEST.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["crop_rel"] and r["dhash"]]
    rows.sort(key=lambda r: (r["source"], r["name"]))

    # 贪心聚类：与已有簇代表距离 <= 阈值则并入
    clusters: list[dict[str, object]] = []
    for row in rows:
        placed = False
        for cluster in clusters:
            if hamming(row["dhash"], cluster["dhash"]) <= HAMMING_THRESHOLD:  # type: ignore[arg-type]
                cluster["members"].append(row)  # type: ignore[union-attr]
                placed = True
                break
        if not placed:
            clusters.append({"dhash": row["dhash"], "repr": row, "members": [row]})

    for index, cluster in enumerate(clusters):
        cluster["cluster_id"] = index
        members = cluster["members"]
        shed = sum(1 for m in members if m["auto_state"] == "shedding")
        cluster["auto_votes"] = f"{shed}/{len(members)} shedding"

    DEDUP.parent.mkdir(parents=True, exist_ok=True)
    with DEDUP.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["cluster_id", "source", "repr_name", "repr_crop", "member_count", "auto_votes"])
        for cluster in clusters:
            repr_row = cluster["repr"]
            writer.writerow(
                [
                    cluster["cluster_id"],
                    repr_row["source"],
                    repr_row["name"],
                    repr_row["crop_rel"],
                    len(cluster["members"]),
                    cluster["auto_votes"],
                ]
            )

    # 生成拼图
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    per_sheet = COLS * ROWS
    cell = THUMB + PAD
    sheet_count = math.ceil(len(clusters) / per_sheet)
    for sheet_index in range(sheet_count):
        canvas = np.full((ROWS * cell, COLS * cell, 3), 245, dtype=np.uint8)
        chunk = clusters[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
        for offset, cluster in enumerate(chunk):
            repr_row = cluster["repr"]
            img = cv2.imdecode(
                np.fromfile(str(CROP_ROOT / str(repr_row["crop_rel"])), dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if img is None:
                continue
            ratio = THUMB / max(img.shape[0], img.shape[1])
            resized = cv2.resize(
                img, (max(1, int(img.shape[1] * ratio)), max(1, int(img.shape[0] * ratio)))
            )
            r, c = divmod(offset, COLS)
            y0 = r * cell + PAD
            x0 = c * cell + PAD
            canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
            label = str(cluster["cluster_id"])
            cv2.rectangle(canvas, (x0, y0), (x0 + 62, y0 + 26), (0, 0, 0), -1)
            cv2.putText(
                canvas,
                label,
                (x0 + 4, y0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
        out = SHEET_DIR / f"sheet_{sheet_index:02d}.jpg"
        cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(str(out))

    print(f"原图 {len(rows)} → 近重复聚类 {len(clusters)} 簇")
    print(f"清单: {DEDUP}")
    print(f"拼图: {sheet_count} 张，目录 {SHEET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

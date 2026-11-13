"""P22 鲁棒性测试与阈值标定。

回答三个问题：

1. 真实场景（640×480 固定机位、隔玻璃、逆光/昏暗、JPEG 压缩）下，
   蜕皮召回最坏还剩多少？
2. 哪一类退化对分类器伤害最大？
3. 服务端阈值应该定在多少，依据是什么？

做法：直接复用线上的 `OnnxStateClassifier.from_path(...).classify(frame)`，
对 test / valid 两个 split 逐档叠加人为退化，统计混淆矩阵并扫阈值。
这样评估路径与线上完全一致，不存在「用训练脚本的预处理」这类偏差。

用法（PowerShell）：

    $env:PYTHONPATH = "server/src"
    $env:PYTHONIOENCODING = "utf-8"
    .\\.venv\\Scripts\\python.exe ml/eval_robustness.py

结果落在 `ml/runs/robustness/summary.json`（该目录被 .gitignore 忽略）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import platform
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Final

import cv2
import numpy as np

from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.shedding import ShedState
from shedguard_server.infra.classifier import OnnxStateClassifier

IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})

#: 正类。召回与精确率都按「蜕皮」算 —— 漏报一次蜕皮比让用户多看一眼贵得多。
POSITIVE_LABEL: Final = "shedding"
NEGATIVE_LABEL: Final = "normal"

#: 阈值扫描范围与步长，与任务书一致。
THRESHOLD_START: Final = 0.30
THRESHOLD_STOP: Final = 0.95
THRESHOLD_STEP: Final = 0.05

#: 选工作点的硬前提：蜕皮召回不低于它，再比精确率。
RECALL_FLOOR: Final = 0.85

#: 线上默认值，只用于对照，不在这里改。
DEFAULT_STATE_MIN_CONFIDENCE: Final = 0.60

DEFAULT_DATASET: Final = "ml/datasets/gecko-state-v2"
DEFAULT_MODEL: Final = "ml/models/gecko-state-v2.onnx"
DEFAULT_OUT: Final = "ml/runs/robustness/summary.json"
DEFAULT_SPLITS: Final = ("test", "valid")


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True, slots=True)
class Sample:
    """一张图及其真实类别索引（按模型的 labels 顺序）。"""

    name: str
    path: pathlib.Path
    label: int


@dataclass(frozen=True, slots=True)
class Degradation:
    """一档退化：`kind` 决定怎么变，`value` 是这一档的强度。"""

    id: str
    group: str
    label: str
    kind: str
    value: float
    note: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group": self.group,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "note": self.note,
        }


#: 五类退化 + 组合档。顺序即执行顺序，也用于给随机数发生器播种。
DEGRADATIONS: Final[tuple[Degradation, ...]] = (
    Degradation("baseline", "baseline", "基线（不退化）", "none", 0.0),
    # a) 固定机位 640×480：整幅画面只有这么多像素。第二、三档假设检测框
    #    只占半帧 / 三分之一帧，即守宫在真实画面里更小 —— 这是 [假设]。
    Degradation("frame-640", "frame", "整帧 640×480", "frame", 640.0),
    Degradation("frame-320", "frame", "半帧 320×240", "frame", 320.0),
    Degradation("frame-213", "frame", "三分之一帧 213×160", "frame", 213.0),
    # b) 传输与存储里的 JPEG 压缩。
    Degradation("jpeg-95", "jpeg", "JPEG 质量 95", "jpeg", 95.0),
    Degradation("jpeg-60", "jpeg", "JPEG 质量 60", "jpeg", 60.0),
    Degradation("jpeg-40", "jpeg", "JPEG 质量 40", "jpeg", 40.0),
    Degradation("jpeg-25", "jpeg", "JPEG 质量 25", "jpeg", 25.0),
    # c) 隔玻璃 + 对焦不准的离焦。
    Degradation("blur-3", "blur", "高斯模糊核 3", "blur", 3.0),
    Degradation("blur-5", "blur", "高斯模糊核 5", "blur", 5.0),
    Degradation("blur-7", "blur", "高斯模糊核 7", "blur", 7.0),
    # d) 曝光与噪声。
    Degradation("bright-0.6", "exposure", "亮度 ×0.6", "brightness", 0.6),
    Degradation("bright-0.8", "exposure", "亮度 ×0.8", "brightness", 0.8),
    Degradation("bright-1.2", "exposure", "亮度 ×1.2", "brightness", 1.2),
    Degradation("noise-5", "noise", "高斯噪声 σ=5", "noise", 5.0),
    Degradation("noise-12", "noise", "高斯噪声 σ=12", "noise", 12.0),
    Degradation("noise-25", "noise", "高斯噪声 σ=25", "noise", 25.0),
    # e) 玻璃反光：叠加一枚椭球渐变高光斑。
    Degradation("glare-mild", "glare", "反光（弱 0.25）", "glare", 0.25),
    Degradation("glare-medium", "glare", "反光（中 0.45）", "glare", 0.45),
    Degradation("glare-strong", "glare", "反光（强 0.65）", "glare", 0.65),
    # f) 组合退化：分辨率 + 离焦 + 偏暗 + 重压缩，按物理发生顺序叠加。
    Degradation("combo", "combo", "组合（640×480+模糊3+亮度0.8+JPEG40）", "combo", 0.0),
)


# ---------------------------------------------------------------- 退化算子
#
# 所有算子输入输出都是 (H, W, 3) 的 uint8 RGB，形状不变 —— `ImageFrame`
# 对形状有严格校验，形状一变就直接抛错。


def degrade_frame_scale(rgb: np.ndarray, frame_long_side: float) -> tuple[np.ndarray, bool]:
    """把画面整体缩到 `frame_long_side × (3/4 · frame_long_side)` 再还原。

    对应「640×480 固定机位」：640 是长边上限，4:3 是画面比例。原图比它大
    才真正丢分辨率；比它小的图不放大（传感器不会凭空多出细节），直接返回。
    """
    height, width = rgb.shape[:2]
    frame_width = frame_long_side
    frame_height = frame_long_side * 0.75
    scale = min(frame_width / width, frame_height / height)
    if scale >= 1.0:
        return rgb, False

    small = cv2.resize(
        rgb,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    restored = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)
    return restored, True


def degrade_jpeg(rgb: np.ndarray, quality: float) -> tuple[np.ndarray, int]:
    """按给定质量真编码再解码一次，返回还原图与实际字节数。"""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buffer = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError(f"JPEG 编码失败: quality={quality}")
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError(f"JPEG 解码失败: quality={quality}")
    return cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB), int(buffer.size)


def degrade_blur(rgb: np.ndarray, kernel: float) -> np.ndarray:
    """高斯模糊。sigma 传 0，让 OpenCV 按核大小推导，核越大越糊。"""
    size = int(kernel)
    return cv2.GaussianBlur(rgb, (size, size), 0)


def degrade_brightness(rgb: np.ndarray, factor: float) -> np.ndarray:
    """整体乘一个曝光系数并截断到 0..255。"""
    scaled = np.clip(rgb.astype(np.float32) * factor, 0.0, 255.0)
    return np.round(scaled).astype(np.uint8)


def degrade_noise(rgb: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """叠加零均值高斯噪声；夜晚高感光度下的画面噪点。"""
    noise = rng.normal(0.0, sigma, size=rgb.shape)
    noisy = np.clip(rgb.astype(np.float32) + noise, 0.0, 255.0)
    return np.round(noisy).astype(np.uint8)


def degrade_glare(rgb: np.ndarray, peak_alpha: float, rng: np.random.Generator) -> np.ndarray:
    """叠加一枚椭球渐变高光斑，模拟隔着玻璃拍到的反射。

    位置、大小、缩放都按固定种子随机，保证同一次运行可复现；`peak_alpha`
    是光斑中心的不透明度，越靠近中心越白、边缘平滑衰减。
    """
    height, width = rgb.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)

    center_x = rng.uniform(0.15, 0.85) * width
    center_y = rng.uniform(0.15, 0.85) * height
    radius_x = rng.uniform(0.30, 0.55) * width
    radius_y = rng.uniform(0.18, 0.40) * height

    distance_sq = ((xs - center_x) / radius_x) ** 2 + ((ys - center_y) / radius_y) ** 2
    falloff = np.clip(1.0 - distance_sq, 0.0, 1.0) ** 2  # 平方衰减，边缘更柔
    alpha = (peak_alpha * falloff)[..., np.newaxis]

    tint = np.array([255.0, 250.0, 240.0], dtype=np.float32)  # 略偏暖的窗光
    blended = rgb.astype(np.float32) * (1.0 - alpha) + tint * alpha
    return np.clip(blended, 0.0, 255.0).round().astype(np.uint8)


def apply_degradation(
    degradation: Degradation, rgb: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """按档位施加退化，返回（退化后的图, 这一档的附加统计）。"""
    kind = degradation.kind
    value = degradation.value

    if kind == "none":
        return rgb, {}
    if kind == "frame":
        restored, downscaled = degrade_frame_scale(rgb, value)
        return restored, {"downscaled": downscaled}
    if kind == "jpeg":
        restored, size = degrade_jpeg(rgb, value)
        return restored, {"jpeg_bytes": size}
    if kind == "blur":
        return degrade_blur(rgb, value), {}
    if kind == "brightness":
        return degrade_brightness(rgb, value), {}
    if kind == "noise":
        return degrade_noise(rgb, value, rng), {}
    if kind == "glare":
        return degrade_glare(rgb, value, rng), {}
    if kind == "combo":
        # 物理顺序：光学（分辨率 → 离焦 → 曝光）→ 编码压缩。
        restored, _ = degrade_frame_scale(rgb, 640.0)
        restored = degrade_blur(restored, 3.0)
        restored = degrade_brightness(restored, 0.8)
        restored, _ = degrade_jpeg(restored, 40.0)
        return restored, {}

    raise ValueError(f"未知的退化类型: {kind!r}")


# ---------------------------------------------------------------- 数据与评估


def load_rgb(path: pathlib.Path) -> np.ndarray:
    """按线上 `decode_image` 的方式解码：读字节 → imdecode → BGR 转 RGB。"""
    payload = path.read_bytes()
    buffer = np.frombuffer(payload, dtype=np.uint8)
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError(f"无法解码图片: {path}")
    return np.ascontiguousarray(cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))


def collect_samples(dataset_root: pathlib.Path, split: str, labels: tuple[str, ...]) -> list[Sample]:
    """按 `<split>/<label>/*.jpg` 收集样本；类别索引取自模型的 labels 顺序。"""
    split_dir = dataset_root / split
    if not split_dir.is_dir():
        raise SystemExit(f"数据集缺少 split 目录: {split_dir}")

    samples: list[Sample] = []
    for label in labels:
        class_dir = split_dir / label
        if not class_dir.is_dir():
            raise SystemExit(f"数据集缺少类别目录: {class_dir}")
        for path in sorted(class_dir.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                samples.append(Sample(name=f"{label}/{path.name}", path=path, label=labels.index(label)))
    if not samples:
        raise SystemExit(f"split 里没有图片: {split_dir}")
    return samples


def summarize_confusion(tn: int, fp: int, fn: int, tp: int) -> dict[str, Any]:
    """由混淆矩阵算指标；分母为零时给 None，避免编造 0 或 1。"""
    total = tn + fp + fn + tp
    return {
        "n": total,
        "accuracy": round((tn + tp) / total, 4) if total else None,
        "shedding_recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
        "shedding_precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "normal_recall": round(tn / (tn + fp), 4) if (tn + fp) else None,
        # 行 = 真实（normal, shedding），列 = 预测（normal, shedding），与训练
        # 侧 summary.json 的 confusion 约定一致。
        "confusion": [[tn, fp], [fn, tp]],
    }


def evaluate_tier(
    classifier: OnnxStateClassifier,
    frames: list[tuple[Sample, np.ndarray]],
    degradation: Degradation,
    tier_index: int,
    seed: int,
) -> dict[str, Any]:
    """整档跑一遍，返回指标与逐图概率（逐图概率供阈值复核用）。"""
    tn = fp = fn = tp = 0
    confidences: list[float] = []
    shedding_probs: list[float] = []
    per_sample: list[dict[str, Any]] = []
    extras: dict[str, Any] = {"downscaled": 0, "jpeg_bytes": []}

    for image_index, (sample, rgb) in enumerate(frames):
        # 每（档位, 图片）一套独立种子：结果可复现，也不受遍历顺序影响。
        rng = np.random.default_rng([seed, tier_index, image_index])
        degraded, stats = apply_degradation(degradation, rgb, rng)

        if "downscaled" in stats and stats["downscaled"]:
            extras["downscaled"] += 1
        if "jpeg_bytes" in stats:
            extras["jpeg_bytes"].append(stats["jpeg_bytes"])

        frame = ImageFrame(
            width=int(degraded.shape[1]), height=int(degraded.shape[0]), rgb=degraded
        )
        prediction = classifier.classify(frame)

        predicted_positive = prediction.state is ShedState.SHEDDING
        actual_positive = sample.label == 1
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive:
            fp += 1
        elif actual_positive:
            fn += 1
        else:
            tn += 1

        confidences.append(prediction.confidence)
        shedding_probs.append(prediction.probabilities.get(POSITIVE_LABEL, 0.0))
        per_sample.append(
            {
                "name": sample.name,
                "label": sample.label,
                "state": prediction.state.value,
                "confidence": round(prediction.confidence, 4),
                "p_shedding": round(prediction.probabilities.get(POSITIVE_LABEL, 0.0), 4),
            }
        )

    result = summarize_confusion(tn, fp, fn, tp)
    result.update(
        {
            "degradation": degradation.id,
            "group": degradation.group,
            "mean_confidence": round(float(np.mean(confidences)), 4),
            "mean_p_shedding": round(float(np.mean(shedding_probs)), 4),
            "downscaled_images": extras["downscaled"],
            "mean_jpeg_bytes": (
                round(float(np.mean(extras["jpeg_bytes"])), 0) if extras["jpeg_bytes"] else None
            ),
            "per_sample": per_sample,
        }
    )
    return result


def calibrate_thresholds(
    per_sample: list[dict[str, Any]], seed_note: str
) -> dict[str, Any]:
    """在基线的逐图概率上扫阈值。

    这里把阈值解释成「p(shedding) ≥ t 就判蜕皮」的决策阈值 —— 这是能直接
    换回召回的杠杆。线上 `state_min_confidence` 的语义是「赢家置信度不足就记
    unknown」，两者不等价，报告里分开说明。
    """
    labels = np.array([row["label"] for row in per_sample], dtype=np.int64)
    probs = np.array([row["p_shedding"] for row in per_sample], dtype=np.float64)

    rows: list[dict[str, Any]] = []
    steps = int(round((THRESHOLD_STOP - THRESHOLD_START) / THRESHOLD_STEP))
    for step in range(steps + 1):
        threshold = round(THRESHOLD_START + step * THRESHOLD_STEP, 2)
        predicted = probs >= threshold
        tp = int(np.sum(predicted & (labels == 1)))
        fp = int(np.sum(predicted & (labels == 0)))
        fn = int(np.sum(~predicted & (labels == 1)))
        tn = int(np.sum(~predicted & (labels == 0)))
        rows.append({"threshold": threshold, **summarize_confusion(tn, fp, fn, tp)})

    eligible = [
        row for row in rows if row["shedding_recall"] is not None and row["shedding_recall"] >= RECALL_FLOOR
    ]
    if eligible:
        # 召回达标的前提下取精确率最高；平手时取更高阈值（更保守、更贴近现状）。
        best = max(eligible, key=lambda row: (row["shedding_precision"] or 0.0, row["threshold"]))
        recommended: dict[str, Any] | None = {
            "threshold": best["threshold"],
            "shedding_recall": best["shedding_recall"],
            "shedding_precision": best["shedding_precision"],
            "accuracy": best["accuracy"],
            "rule": f"在 shedding 召回 ≥ {RECALL_FLOOR} 的阈值里取 precision 最高者；平手取更高阈值",
            "eligible_thresholds": [row["threshold"] for row in eligible],
        }
    else:
        recommended = None

    at_default = next((row for row in rows if row["threshold"] == DEFAULT_STATE_MIN_CONFIDENCE), None)
    return {
        "split": "valid",
        "n": int(len(labels)),
        "positive_label": POSITIVE_LABEL,
        "rule": "p(shedding) >= threshold 判 shedding，否则 normal",
        "seed_note": seed_note,
        "sweep": rows,
        "current_default": {"value": DEFAULT_STATE_MIN_CONFIDENCE, "point": at_default},
        "recommended": recommended,
    }


def deployment_as_is(
    per_sample: list[dict[str, Any]], min_confidence: float, *, include_misses: bool = False
) -> dict[str, Any]:
    """按线上现行语义复核：argmax 出状态，赢家置信度 < 阈值就记 unknown。

    unknown 不是「正常」也不是「蜕皮」，但它会在按日聚合里被当作「没看见」，
    连续 unknown 就等于漏报 —— 所以这里同时给出「unknown 算漏报」的口径。
    """
    unknown = 0
    observed_tp = observed_fn = observed_tn = observed_fp = 0
    all_tp = all_fn = 0
    confident_misses: list[dict[str, Any]] = []

    for row in per_sample:
        actual_positive = row["label"] == 1
        if row["confidence"] < min_confidence:
            unknown += 1
            if actual_positive:
                all_fn += 1
            continue

        predicted_positive = row["state"] == POSITIVE_LABEL
        if predicted_positive and actual_positive:
            observed_tp += 1
            all_tp += 1
        elif predicted_positive:
            observed_fp += 1
        elif actual_positive:
            observed_fn += 1
            all_fn += 1
            confident_misses.append(
                {"name": row["name"], "confidence": row["confidence"], "p_shedding": row["p_shedding"]}
            )
        else:
            observed_tn += 1

    observed_total = observed_tp + observed_fp + observed_fn + observed_tn
    return {
        "min_confidence": min_confidence,
        "semantics": "argmax 状态；赢家置信度 < min_confidence 记 unknown",
        "unknown_count": unknown,
        "unknown_rate": round(unknown / len(per_sample), 4),
        "coverage": round(1.0 - unknown / len(per_sample), 4),
        "observed_accuracy": (
            round((observed_tp + observed_tn) / observed_total, 4) if observed_total else None
        ),
        "observed_shedding_recall": (
            round(observed_tp / (observed_tp + observed_fn), 4) if (observed_tp + observed_fn) else None
        ),
        "all_shedding_recall": round(all_tp / (all_tp + all_fn), 4) if (all_tp + all_fn) else None,
        "confident_miss_count": len(confident_misses),
        "confident_misses": confident_misses[:20] if include_misses else [],
    }


def abstain_sweep(per_sample: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """在同一个阈值网格上复核现行语义：抬高 `state_min_confidence` 到底换回了什么。

    现行实现只看赢家置信度，低于阈值记 unknown —— 它不会把 normal 改成
    shedding，所以对召回基本没有正作用，只是让系统更少下结论。
    """
    rows: list[dict[str, Any]] = []
    steps = int(round((THRESHOLD_STOP - THRESHOLD_START) / THRESHOLD_STEP))
    for step in range(steps + 1):
        threshold = round(THRESHOLD_START + step * THRESHOLD_STEP, 2)
        point = deployment_as_is(per_sample, threshold)
        rows.append(
            {
                "min_confidence": threshold,
                "unknown_count": point["unknown_count"],
                "unknown_rate": point["unknown_rate"],
                "observed_accuracy": point["observed_accuracy"],
                "observed_shedding_recall": point["observed_shedding_recall"],
                "all_shedding_recall": point["all_shedding_recall"],
            }
        )
    return rows


def threshold_grid(
    results: dict[str, dict[str, Any]], thresholds: list[float]
) -> dict[str, dict[str, Any]]:
    """把若干候选阈值套到每一档退化图上一遍，看退化会不会吃掉阈值的余量。"""
    grid: dict[str, dict[str, Any]] = {}
    for threshold in thresholds:
        key = f"{threshold:.2f}"
        grid[key] = {}
        for degradation in DEGRADATIONS:
            rows = results[degradation.id]["per_sample"]
            predicted = [row["p_shedding"] >= threshold for row in rows]
            tp = sum(1 for row, hit in zip(rows, predicted) if hit and row["label"] == 1)
            fn = sum(1 for row, hit in zip(rows, predicted) if not hit and row["label"] == 1)
            fp = sum(1 for row, hit in zip(rows, predicted) if hit and row["label"] == 0)
            tn = sum(1 for row, hit in zip(rows, predicted) if not hit and row["label"] == 0)
            metrics = summarize_confusion(tn, fp, fn, tp)
            grid[key][degradation.id] = {
                "shedding_recall": metrics["shedding_recall"],
                "shedding_precision": metrics["shedding_precision"],
                "accuracy": metrics["accuracy"],
            }
    return grid


# ---------------------------------------------------------------- 输出


def display_width(text: str) -> int:
    """中文按两个字符宽算，纯文本表格才能对齐。"""
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def pad(text: str, width: int, right: bool = False) -> str:
    filling = " " * max(0, width - display_width(text))
    return filling + text if right else text + filling


def format_table(headers: list[str], rows: list[list[str]], right_columns: set[int]) -> str:
    widths = [display_width(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], display_width(cell))

    lines = ["  ".join(pad(header, widths[i]) for i, header in enumerate(headers))]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append(
            "  ".join(pad(cell, widths[i], right=i in right_columns) for i, cell in enumerate(row))
        )
    return "\n".join(lines)


def fmt(value: Any, digits: int = 4) -> str:
    """把 None 打成破折号，别把「没有样本」伪装成 0。"""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


# ---------------------------------------------------------------- 主流程


def main() -> None:
    parser = argparse.ArgumentParser(description="P22 蜕皮状态分类器鲁棒性测试与阈值标定")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--splits", default=",".join(DEFAULT_SPLITS))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-per-class", type=int, default=0, help="每类最多取几张，0 表示全量")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()
    started_at = time.monotonic()

    dataset_root = pathlib.Path(args.dataset)
    model_path = pathlib.Path(args.model)
    classifier = OnnxStateClassifier.from_path(model_path)
    labels = classifier.labels
    if POSITIVE_LABEL not in labels or NEGATIVE_LABEL not in labels:
        raise SystemExit(f"模型标签里没有 {NEGATIVE_LABEL}/{POSITIVE_LABEL}: {labels}")

    print(f"模型: {classifier.name}  输入 {classifier.input_size}×{classifier.input_size}  标签 {list(labels)}")

    splits = [item.strip() for item in args.splits.split(",") if item.strip()]
    report: dict[str, Any] = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": {
            "onnx": args.model,
            "name": classifier.name,
            "input_size": classifier.input_size,
            "labels": list(labels),
        },
        "dataset": {"root": args.dataset, "splits": splits},
        "settings": {
            "seed": args.seed,
            "max_per_class": args.max_per_class,
            "positive_label": POSITIVE_LABEL,
            "recall_floor_for_operating_point": RECALL_FLOOR,
            "threshold_sweep": {
                "start": THRESHOLD_START,
                "stop": THRESHOLD_STOP,
                "step": THRESHOLD_STEP,
            },
            "default_state_min_confidence": DEFAULT_STATE_MIN_CONFIDENCE,
        },
        "degradations": [degradation.as_json() for degradation in DEGRADATIONS],
        "splits": {},
        "thresholds": None,
    }

    images_evaluated = 0
    for split in splits:
        samples = collect_samples(dataset_root, split, labels)
        if args.max_per_class > 0:
            kept: list[Sample] = []
            for label in labels:
                group = [sample for sample in samples if labels[sample.label] == label][: args.max_per_class]
                kept.extend(group)
            samples = kept

        print(f"\n=== split: {split}（{len(samples)} 张）加载中 ===", flush=True)
        images_evaluated += len(samples)
        frames: list[tuple[Sample, np.ndarray]] = [(sample, load_rgb(sample.path)) for sample in samples]
        counts = {
            label: sum(1 for sample in samples if labels[sample.label] == label) for label in labels
        }

        results: dict[str, Any] = {}
        for tier_index, degradation in enumerate(DEGRADATIONS):
            print(f"  [{tier_index + 1}/{len(DEGRADATIONS)}] {degradation.label} ...", flush=True)
            result = evaluate_tier(classifier, frames, degradation, tier_index, args.seed)
            results[degradation.id] = result

        baseline = results["baseline"]
        for degradation in DEGRADATIONS:
            row = results[degradation.id]
            row["accuracy_delta"] = (
                round(row["accuracy"] - baseline["accuracy"], 4)
                if row["accuracy"] is not None and baseline["accuracy"] is not None
                else None
            )
            row["shedding_recall_delta"] = (
                round(row["shedding_recall"] - baseline["shedding_recall"], 4)
                if row["shedding_recall"] is not None and baseline["shedding_recall"] is not None
                else None
            )

        deployment = {
            degradation.id: deployment_as_is(
                results[degradation.id]["per_sample"],
                DEFAULT_STATE_MIN_CONFIDENCE,
                include_misses=degradation.id == "baseline",
            )
            for degradation in DEGRADATIONS
        }
        report["splits"][split] = {
            "counts": counts,
            "n": len(samples),
            "results": results,
            "deployment_at_min_confidence": deployment,
        }

        headers = ["档位", "n", "准确率", "shed召回", "shed精确", "normal召回", "TN/FP/FN/TP", "Δ准确率"]
        rows: list[list[str]] = []
        for degradation in DEGRADATIONS:
            row = results[degradation.id]
            tn, fp = row["confusion"][0]
            fn, tp = row["confusion"][1]
            rows.append(
                [
                    degradation.label,
                    str(row["n"]),
                    fmt(row["accuracy"]),
                    fmt(row["shedding_recall"]),
                    fmt(row["shedding_precision"]),
                    fmt(row["normal_recall"]),
                    f"{tn}/{fp}/{fn}/{tp}",
                    fmt(row["accuracy_delta"]),
                ]
            )
        print()
        print(format_table(headers, rows, right_columns={1, 2, 3, 4, 5, 6, 7}))

        if split == "valid" and "baseline" in results:
            calibration = calibrate_thresholds(
                results["baseline"]["per_sample"], "阈值扫描基于 valid 基线的 p(shedding)"
            )
            report["thresholds"] = calibration

            print("\n=== 阈值标定（valid，p(shedding) ≥ t 判 shedding）===")
            t_rows = [
                [
                    f"{row['threshold']:.2f}",
                    fmt(row["shedding_recall"]),
                    fmt(row["shedding_precision"]),
                    fmt(row["accuracy"]),
                ]
                for row in calibration["sweep"]
            ]
            print(format_table(["阈值", "shed召回", "shed精确", "准确率"], t_rows, {0, 1, 2, 3}))

            recommended = calibration["recommended"]
            if recommended:
                print(
                    f"\n建议工作点: t={recommended['threshold']:.2f} "
                    f"（召回 {recommended['shedding_recall']:.4f} / 精确 {recommended['shedding_precision']:.4f}）"
                )
            else:
                print(f"\n没有阈值能让召回达到 {RECALL_FLOOR}")

            # 现行语义（只当 abstain 用）在同一网格上的表现，用来看 0.6 落在哪。
            abstain = abstain_sweep(results["baseline"]["per_sample"])
            calibration["abstain_sweep"] = abstain
            print("\n=== 现行语义复核：argmax + 赢家置信度 < t 记 unknown（valid）===")
            a_rows = [
                [
                    f"{row['min_confidence']:.2f}",
                    fmt(row["unknown_rate"]),
                    fmt(row["observed_shedding_recall"]),
                    fmt(row["all_shedding_recall"]),
                    fmt(row["observed_accuracy"]),
                ]
                for row in abstain
            ]
            print(
                format_table(
                    ["阈值", "unknown率", "可观测召回", "unknown算漏报", "可观测准确率"],
                    a_rows,
                    {0, 1, 2, 3, 4},
                )
            )

            at_06 = next(
                (row for row in abstain if row["min_confidence"] == DEFAULT_STATE_MIN_CONFIDENCE),
                None,
            )
            if at_06 is not None:
                print(
                    f"现行 @0.6: unknown {at_06['unknown_rate']:.4f}（{at_06['unknown_count']} 张），"
                    f"可观测召回 {fmt(at_06['observed_shedding_recall'])}，"
                    f"unknown 算漏报时召回 {fmt(at_06['all_shedding_recall'])}"
                )

            # 候选阈值在退化图上的表现：退化会不会吃掉阈值的召回余量。
            candidates = (
                sorted({0.50, DEFAULT_STATE_MIN_CONFIDENCE, recommended["threshold"]})
                if recommended
                else [0.50, DEFAULT_STATE_MIN_CONFIDENCE]
            )
            grid = threshold_grid(results, candidates)
            calibration["recall_grid"] = grid

            print("\n=== 候选阈值在各退化档上的 shedding 召回（valid）===")
            g_headers = ["档位"] + [f"召回@{key}" for key in grid]
            g_rows = [
                [degradation.label] + [fmt(grid[key][degradation.id]["shedding_recall"]) for key in grid]
                for degradation in DEGRADATIONS
            ]
            print(format_table(g_headers, g_rows, set(range(1, len(g_headers)))))

            print("\n=== 现行语义 @0.6 在各退化档上的覆盖率（valid）===")
            d_rows = [
                [
                    degradation.label,
                    fmt(deployment[degradation.id]["unknown_rate"]),
                    fmt(deployment[degradation.id]["observed_shedding_recall"]),
                    fmt(deployment[degradation.id]["all_shedding_recall"]),
                ]
                for degradation in DEGRADATIONS
            ]
            print(format_table(["档位", "unknown率", "可观测召回", "unknown算漏报"], d_rows, {1, 2, 3}))

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report["run"] = {
        "elapsed_seconds": round(time.monotonic() - started_at, 1),
        "images_evaluated": images_evaluated,
        "inferences": images_evaluated * len(DEGRADATIONS),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
        },
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {out_path}（{report['run']['elapsed_seconds']} s，{images_evaluated} 张 × {len(DEGRADATIONS)} 档）")


if __name__ == "__main__":
    main()
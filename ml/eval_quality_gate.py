"""C6 输入质量门的标定与验收脚本。

回答一个问题：**质量门真的按预期工作吗？** 也就是在 349 张验证图 × 9 档退化上，
把「太糊 / 太暗 / 过曝 / 没找到守宫」拦下来之后，剩下的图准确率是否变高、
蜕皮召回还剩多少、每档条件各被哪条门拦掉多少张。

做法与 `ml/eval_robustness.py` 完全一致：直接复用线上的检测器、裁剪函数与分类器，
退化图由 `eval_robustness.apply_degradation` 生成，指标在**检测框外扩 8% 后缩放到
224×224 的裁剪图**上计算 —— 与分类器的实际输入逐像素一致，阈值才能迁移。

与 `eval_robustness.py` 的区别：那边问「模型在退化下还剩多少」，这边问「门拦得对不对」。
所以这里额外统计每档的漏检数、sharpness 中位数、按原因拆分的拦截数，以及
「干净且判对」子集上的单门误杀率。

用法（PowerShell）：

    cd ml
    $env:PYTHONIOENCODING = "utf-8"
    .\\..\\.venv\\Scripts\\python.exe eval_quality_gate.py            # 全量，约 10–15 分钟
    .\\..\\.venv\\Scripts\\python.exe eval_quality_gate.py --limit 40 # 快速验证逻辑

结果落在 `ml/runs/quality-gate/eval.json`（该目录被 .gitignore 忽略）。

样本顺序：为了 `--limit N` 的调试切片仍同时包含两个类别，收集后按类别轮转交错
（normal[0], shedding[0], normal[1], shedding[1], …）。全量运行覆盖全部样本，
交错只影响遍历顺序，不影响统计口径。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import platform
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

PROJECT_ROOT: Final = pathlib.Path(__file__).resolve().parents[1]
# 与 `server/scripts/device_sim.py` 同一写法：让脚本能 import 到 server 的包。
sys.path.insert(0, str(PROJECT_ROOT / "server" / "src"))

# isort: split
# 上面这行 `sys.path` 之后才能 import server 的包，与 `ml/eval_robustness.py` 同一套路。
# `# isort: split` 让 ruff 把下面两块当独立区段：本文件既可能从 `ml/` 跑、
# 也可能从仓库根跑，两种工作目录下 ruff 对「谁是第三方包」的判断不同，
# 不隔开就会出现「在 ml/ 下过、在根目录下报 I001」的假失败。
from eval_robustness import (
    DEGRADATIONS,
    Sample,
    apply_degradation,
    fmt,
    format_table,
    load_rgb,
)

# isort: split
from shedguard_server.domain.imaging import ImageFrame
from shedguard_server.domain.metrics import _lab_lightness
from shedguard_server.domain.shedding import crop_box, crop_frame
from shedguard_server.infra.classifier import OnnxStateClassifier
from shedguard_server.infra.detector import OnnxDetector

IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})

#: 与标定时一致的随机种子。只有 glare（高光斑位置）与 noise 用得到它。
SEED: Final = 20261125

#: 指标计算分辨率。必须与分类器输入边长一致，否则阈值不可迁移。
MEASURE_SIZE: Final = 224

#: 通道值达到这个数就算削顶：数据已经丢了，不是浅色。
SATURATED_LEVEL: Final = 250

#: 检测框外扩比例，与线上 `DEFAULT_STATE_CROP_PADDING` 一致。
CROP_PADDING: Final = 0.08

#: 质量门阈值，来源是本次标定（349 张 × 9 档）。
MIN_SHARPNESS: Final = 25.0
MIN_LIGHTNESS: Final = 18.0
MAX_SATURATED: Final = 0.20

#: 判定原因。字符串值与 `domain/quality.py` 的 `QualityReason` 逐字一致。
REASON_TOO_BLURRY: Final = "too_blurry"
REASON_TOO_DARK: Final = "too_dark"
REASON_OVEREXPOSED: Final = "overexposed"
REASON_NO_SUBJECT: Final = "no_subject"

REASONS: Final = (
    REASON_TOO_BLURRY,
    REASON_TOO_DARK,
    REASON_OVEREXPOSED,
    REASON_NO_SUBJECT,
)

POSITIVE_LABEL: Final = "shedding"
NEGATIVE_LABEL: Final = "normal"

#: 本脚本要跑的 9 档条件，顺序即表格顺序（也是随机数播种的档位下标）。
CONDITION_IDS: Final = (
    "baseline",
    "blur-3",
    "blur-5",
    "blur-7",
    "bright-0.6",
    "bright-1.2",
    "glare-strong",
    "combo",
    "frame-640",
)

DEFAULT_DATASET: Final = "ml/datasets/gecko-state-v2/valid"
DEFAULT_DETECTOR: Final = "ml/models/gecko-det.onnx"
DEFAULT_CLASSIFIER: Final = "ml/models/gecko-state-v2.onnx"
DEFAULT_OUT: Final = "ml/runs/quality-gate/eval.json"

#: 主 agent 一次性探针标定出的基线数字，本脚本必须复现它们。
#: 键为条件 id；`accuracy` / `shedding_recall` 的分母是**全部**图片（漏检算错）。
EXPECTED: Final[dict[str, dict[str, float]]] = {
    "baseline": {"misses": 8, "sharpness_p50": 518.6, "accuracy": 0.934, "shedding_recall": 0.923},
    "blur-3": {"misses": 30, "sharpness_p50": 98.0, "accuracy": 0.819, "shedding_recall": 0.615},
    "blur-5": {"misses": 47, "sharpness_p50": 46.9, "accuracy": 0.734, "shedding_recall": 0.451},
    "blur-7": {"misses": 81, "sharpness_p50": 19.3, "accuracy": 0.625, "shedding_recall": 0.319},
    "combo": {"misses": 48, "sharpness_p50": 71.5, "accuracy": 0.765, "shedding_recall": 0.571},
    "bright-1.2": {"misses": 7, "sharpness_p50": 705.9, "accuracy": 0.928, "shedding_recall": 0.923},
}

#: 清晰度单门在「干净且判对」子集上的预期拦截率。
EXPECTED_SHARPNESS_GATE: Final[dict[str, float]] = {
    "baseline": 0.012,
    "blur-7": 0.62,
    "blur-5": 0.25,
}

#: 判定「一致」的容差：比率 ±0.02；漏检数 ±1 张；p50 相对误差 ±2%。
RATE_TOLERANCE: Final = 0.02
MISS_TOLERANCE: Final = 1
P50_RELATIVE_TOLERANCE: Final = 0.02


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True, slots=True)
class CropMetrics:
    """一张 224×224 裁剪图的三项质量指标。

    与 `domain/quality.py` 的 `QualityMetrics` 字段一致，但这里独立定义，
    避免标定脚本 import 正在并行修改的服务端模块。
    """

    sharpness: float
    lightness: float
    saturated: float


@dataclass(frozen=True, slots=True)
class ImageOutcome:
    """一张图在某一档条件下的全部观测结果。

    关键设计：**分类器一律照跑**，不管质量门拦没拦。
    `predicted` 因此是「如果没有这道门，模型会说什么」——
    无门准确率与无门召回都要靠它算，被门拦下的图也得有分类结果，
    否则「无门」那一列统计的其实是被门挑剩下的子集，数字会假性偏低。

    `detected` 为假表示检测器没找到守宫（此时指标与预测都是 None）；
    `gate_reason` 为 None 表示过了质量门，否则是被拦下的原因。
    """

    name: str
    actual: str
    detected: bool
    sharpness: float | None
    lightness: float | None
    saturated: float | None
    gate_reason: str | None
    predicted: str | None
    confidence: float | None
    p_shedding: float | None

    @property
    def correct(self) -> bool:
        """无门口径下是否判对。漏检算错（没给出结论就等于没判对）。"""
        return self.predicted is not None and self.predicted == self.actual

    @property
    def passed(self) -> bool:
        """是否过了质量门、拿到结论（被门拦下或漏检都算没过）。"""
        return self.detected and self.gate_reason is None

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "actual": self.actual,
            "detected": self.detected,
            "sharpness": round(self.sharpness, 2) if self.sharpness is not None else None,
            "lightness": round(self.lightness, 2) if self.lightness is not None else None,
            "saturated": round(self.saturated, 4) if self.saturated is not None else None,
            "gate_reason": self.gate_reason,
            "predicted": self.predicted,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "p_shedding": round(self.p_shedding, 4) if self.p_shedding is not None else None,
        }


# ---------------------------------------------------------------- 质量门
#
# ⚠️ 这里的 `measure_crop_quality` / `verdict_from_metrics` / `evaluate_quality`
# 三个函数与 `server/src/shedguard_server/domain/quality.py` 必须保持一致，
# 改一处要改两处：缩放插值、灰度转换、饱和阈值、判定顺序（太糊 → 太暗 → 过曝）
# 任何一处漂移，标定出来的阈值就不再适用于线上。


def measure_crop_quality(crop_rgb_224: NDArray[np.uint8]) -> CropMetrics:
    """量一张**已缩放到 224×224** 的裁剪图。

    缩放用 `INTER_LINEAR`、灰度用 `COLOR_RGB2GRAY`，与线上逐字一致 ——
    换插值方式会让拉普拉斯方差整体漂移，阈值就得重标。
    """
    if crop_rgb_224.shape[:2] != (MEASURE_SIZE, MEASURE_SIZE):
        resized: NDArray[np.uint8] = cv2.resize(
            crop_rgb_224, (MEASURE_SIZE, MEASURE_SIZE), interpolation=cv2.INTER_LINEAR
        )
    else:
        resized = crop_rgb_224

    gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # `_lab_lightness` 是 `domain/metrics.py` 的私有函数，按任务书要求直接复用：
    # 重写一份 L* 反而更容易与线上算出两个数。它要求输入是 0–1 的 float32。
    lightness = float(_lab_lightness(resized.astype(np.float32) / 255.0).mean())
    saturated = float((resized.max(axis=2) >= SATURATED_LEVEL).mean())
    return CropMetrics(sharpness=sharpness, lightness=lightness, saturated=saturated)


def verdict_from_metrics(
    metrics: CropMetrics,
    *,
    min_sharpness: float = MIN_SHARPNESS,
    min_lightness: float = MIN_LIGHTNESS,
    max_saturated: float = MAX_SATURATED,
) -> str | None:
    """按「太糊 → 太暗 → 过曝」的顺序判定，命中即返回，只报第一条。

    顺序是产品决策：一张图同时满足多条时只给用户一个重拍理由，
    而且先修对焦比先修曝光更常见。返回值与 `QualityReason` 的字符串值一致。
    """
    if metrics.sharpness < min_sharpness:
        return REASON_TOO_BLURRY
    if metrics.lightness < min_lightness:
        return REASON_TOO_DARK
    if metrics.saturated > max_saturated:
        return REASON_OVEREXPOSED
    return None


def evaluate_quality(
    crop_rgb_224: NDArray[np.uint8],
    *,
    min_sharpness: float = MIN_SHARPNESS,
    min_lightness: float = MIN_LIGHTNESS,
    max_saturated: float = MAX_SATURATED,
) -> str | None:
    """量指标并判定，返回原因字符串或 None（通过）。

    与 `server/src/shedguard_server/domain/quality.py` 的 `evaluate_quality`
    必须保持一致，改一处要改两处。
    """
    return verdict_from_metrics(
        measure_crop_quality(crop_rgb_224),
        min_sharpness=min_sharpness,
        min_lightness=min_lightness,
        max_saturated=max_saturated,
    )


# ---------------------------------------------------------------- 数据


def resolve_input_path(raw: str) -> pathlib.Path:
    """解析输入路径：绝对路径原样返回，相对路径先按当前目录、再按仓库根目录找。

    默认值是仓库根相对的 `ml/models/...`，但本脚本常从 `ml/` 目录里跑；
    两种工作目录都能用，才不至于因为 `cd` 的位置不同而报「模型不存在」。
    两个位置都不存在时返回按当前目录解析的结果，让下游报出原始路径。
    """
    path = pathlib.Path(raw)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    from_root = PROJECT_ROOT / path
    return from_root if from_root.exists() else path


def resolve_output_path(raw: str) -> pathlib.Path:
    """解析输出路径：绝对路径原样返回，相对路径**一律相对仓库根目录**。

    输出文件通常还不存在，不能像输入那样「哪找到算哪」；默认值
    `ml/runs/quality-gate/eval.json` 写的就是仓库根相对的路径，
    若按当前目录解析，从 `ml/` 里跑会歪成 `ml/ml/runs/...`。
    """
    path = pathlib.Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def collect_valid_samples(split_dir: pathlib.Path, labels: tuple[str, ...]) -> list[Sample]:
    """按 `<split>/<label>/*.jpg` 收集样本，再按类别轮转交错。

    交错是为了 `--limit N` 的调试切片仍同时包含 normal 与 shedding ——
    否则前 40 张全是 normal，蜕皮召回永远是「—」，等于没验证到召回逻辑。
    """
    if not split_dir.is_dir():
        raise SystemExit(f"数据集目录不存在: {split_dir}")

    buckets: dict[str, list[Sample]] = {}
    for label in labels:
        class_dir = split_dir / label
        if not class_dir.is_dir():
            raise SystemExit(f"数据集缺少类别目录: {class_dir}")
        buckets[label] = [
            Sample(name=f"{label}/{path.name}", path=path, label=labels.index(label))
            for path in sorted(class_dir.iterdir())
            if path.suffix.lower() in IMAGE_SUFFIXES
        ]

    samples: list[Sample] = []
    cursors = dict.fromkeys(labels, 0)
    remaining = sum(len(items) for items in buckets.values())
    while remaining:
        for label in labels:
            index = cursors[label]
            if index < len(buckets[label]):
                samples.append(buckets[label][index])
                cursors[label] = index + 1
                remaining -= 1
    return samples


def crop_to_measure_size(frame: ImageFrame, box: tuple[int, int, int, int]) -> ImageFrame:
    """按检测框裁出守宫，再缩放到 224×224 —— 质量指标与分类器都吃这张图。"""
    crop = crop_frame(frame, box)
    resized = cv2.resize(
        crop.rgb, (MEASURE_SIZE, MEASURE_SIZE), interpolation=cv2.INTER_LINEAR
    )
    return ImageFrame(
        width=MEASURE_SIZE, height=MEASURE_SIZE, rgb=np.ascontiguousarray(resized)
    )


# ---------------------------------------------------------------- 评估


def evaluate_image(
    detector: OnnxDetector,
    classifier: OnnxStateClassifier,
    sample: Sample,
    actual: str,
    degraded: NDArray[np.uint8],
) -> ImageOutcome:
    """对一张已退化的图跑完整链路：检测 → 裁剪缩放 → 质量门 → 分类。"""
    height, width = degraded.shape[:2]
    frame = ImageFrame(width=width, height=height, rgb=np.ascontiguousarray(degraded))

    detection = detector.detect(frame)
    if detection is None:
        # 画面里没有守宫：门直接判 no_subject，分类器不发言。
        return ImageOutcome(
            name=sample.name,
            actual=actual,
            detected=False,
            sharpness=None,
            lightness=None,
            saturated=None,
            gate_reason=REASON_NO_SUBJECT,
            predicted=None,
            confidence=None,
            p_shedding=None,
        )

    box = crop_box(detection.box, width=width, height=height, padding=CROP_PADDING)
    measured = crop_to_measure_size(frame, box)
    metrics = measure_crop_quality(measured.rgb)
    reason = verdict_from_metrics(metrics)

    # 门拦不拦都照跑分类器：无门准确率/召回统计的是「模型原本会说什么」，
    # 被拦下的图缺了预测，「无门」那一列就变成了被门挑剩的子集，会假性偏低。
    # 多花的是推理时间（349×9 次），换来的是两列口径真正可比。
    prediction = classifier.classify(measured)

    return ImageOutcome(
        name=sample.name,
        actual=actual,
        detected=True,
        sharpness=metrics.sharpness,
        lightness=metrics.lightness,
        saturated=metrics.saturated,
        gate_reason=reason,
        predicted=prediction.state.value,
        confidence=prediction.confidence,
        p_shedding=prediction.probabilities.get(POSITIVE_LABEL, 0.0),
    )


def summarize_condition(outcomes: list[ImageOutcome]) -> dict[str, Any]:
    """把一档条件的所有逐图结果汇总成指标。

    「无门」口径：分母是**全部**图片，漏检算错 —— 与基线表的数字对齐。
    「门后」口径：分母是真正过了门、拿到结论的图片，衡量门拦完之后的质量。
    """
    total = len(outcomes)
    detected = [row for row in outcomes if row.detected]
    passed = [row for row in outcomes if row.passed]
    sharpness = [row.sharpness for row in detected if row.sharpness is not None]
    lightness = [row.lightness for row in detected if row.lightness is not None]

    shedding = [row for row in outcomes if row.actual == POSITIVE_LABEL]
    passed_shedding = [row for row in passed if row.actual == POSITIVE_LABEL]
    blocked = Counter(row.gate_reason for row in detected if row.gate_reason is not None)

    correct_no_gate = sum(1 for row in detected if row.correct)
    correct_gated = sum(1 for row in passed if row.correct)

    return {
        "n": total,
        "misses": total - len(detected),
        "miss_rate": round((total - len(detected)) / total, 4) if total else None,
        "sharpness_p50": round(float(np.median(sharpness)), 1) if sharpness else None,
        "sharpness_p10": (
            round(float(np.percentile(sharpness, 10)), 1) if sharpness else None
        ),
        "sharpness_p90": (
            round(float(np.percentile(sharpness, 90)), 1) if sharpness else None
        ),
        "lightness_p50": round(float(np.median(lightness)), 1) if lightness else None,
        # 无门：漏检与误判都算错。
        "accuracy_no_gate": round(correct_no_gate / total, 4) if total else None,
        "shedding_recall_no_gate": (
            round(
                sum(1 for row in shedding if row.predicted == POSITIVE_LABEL) / len(shedding),
                4,
            )
            if shedding
            else None
        ),
        # 门后：只看真正给出结论的那部分。
        "passed": len(passed),
        "coverage": round(len(passed) / total, 4) if total else None,
        "accuracy_gated": round(correct_gated / len(passed), 4) if passed else None,
        "shedding_recall_gated": (
            round(
                sum(1 for row in passed_shedding if row.predicted == POSITIVE_LABEL)
                / len(passed_shedding),
                4,
            )
            if passed_shedding
            else None
        ),
        "blocks": {reason: blocked.get(reason, 0) for reason in REASONS},
        "blocked_total": sum(blocked.values()),
    }


def summarize_sharpness_gate(
    per_condition: dict[str, list[ImageOutcome]],
    clean_names: set[str],
    threshold: float,
) -> list[dict[str, Any]]:
    """只开清晰度门时，各档条件在「干净且判对」子集上的拦截率。

    分母只算这一档里**检测到**的干净样本：没检测到的图根本没走到门，
    把它算成「门拦下的」会虚高拦截率。所以这里同时报出参与张数。
    """
    rows: list[dict[str, Any]] = []
    for condition_id in CONDITION_IDS:
        subset = [
            row
            for row in per_condition[condition_id]
            if row.name in clean_names and row.detected and row.sharpness is not None
        ]
        blocked = sum(1 for row in subset if row.sharpness is not None and row.sharpness < threshold)
        rows.append(
            {
                "condition": condition_id,
                "n": len(subset),
                "blocked": blocked,
                "rate": round(blocked / len(subset), 4) if subset else None,
            }
        )
    return rows


# ---------------------------------------------------------------- 对照


#: 基线表的字段名 → 本脚本统计字典里的键名。
#: 基线表写「无门准确率」，脚本内部叫 `accuracy_no_gate`，这里显式对上，避免悄悄取错键。
EXPECTED_FIELD_ALIASES: Final[dict[str, str]] = {
    "accuracy": "accuracy_no_gate",
    "shedding_recall": "shedding_recall_no_gate",
}


def compare_with_expected(stats: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """把实测值与基线表逐项对比，标出是否落在容差内。"""
    comparisons: list[dict[str, Any]] = []
    for condition_id, expected in EXPECTED.items():
        actual = stats[condition_id]
        for field_name, expected_value in expected.items():
            measured = actual[EXPECTED_FIELD_ALIASES.get(field_name, field_name)]
            if measured is None:
                delta = None
                consistent = False
            elif field_name == "misses":
                delta = int(measured) - int(expected_value)
                consistent = abs(delta) <= MISS_TOLERANCE
            elif field_name == "sharpness_p50":
                delta = round(float(measured) - float(expected_value), 1)
                consistent = (
                    abs(float(measured) - float(expected_value)) / float(expected_value)
                    <= P50_RELATIVE_TOLERANCE
                )
            else:
                delta = round(float(measured) - float(expected_value), 4)
                consistent = abs(delta) <= RATE_TOLERANCE
            comparisons.append(
                {
                    "condition": condition_id,
                    "metric": field_name,
                    "expected": expected_value,
                    "measured": measured,
                    "delta": delta,
                    "consistent": consistent,
                }
            )
    return comparisons


def compare_sharpness_gate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清晰度单门的拦截率与基线对比。"""
    comparisons: list[dict[str, Any]] = []
    by_id = {row["condition"]: row for row in rows}
    for condition_id, expected_value in EXPECTED_SHARPNESS_GATE.items():
        measured = by_id[condition_id]["rate"]
        delta = round(float(measured) - expected_value, 4) if measured is not None else None
        comparisons.append(
            {
                "condition": condition_id,
                "metric": "sharpness_gate_block_rate",
                "expected": expected_value,
                "measured": measured,
                "delta": delta,
                "consistent": delta is not None and abs(delta) <= RATE_TOLERANCE,
            }
        )
    return comparisons


# ---------------------------------------------------------------- 主流程


def build_conditions() -> tuple[Any, ...]:
    """按 `CONDITION_IDS` 的顺序取出退化档，档位定义不在这里重复一遍。"""
    by_id = {degradation.id: degradation for degradation in DEGRADATIONS}
    missing = [condition_id for condition_id in CONDITION_IDS if condition_id not in by_id]
    if missing:
        raise SystemExit(f"eval_robustness 里缺少这些退化档: {missing}")
    return tuple(by_id[condition_id] for condition_id in CONDITION_IDS)


def run(
    samples: list[Sample],
    labels: tuple[str, ...],
    detector: OnnxDetector,
    classifier: OnnxStateClassifier,
    seed: int,
    verbose: bool,
) -> tuple[dict[str, list[ImageOutcome]], float]:
    """逐图 × 逐档跑完整链路，返回（每档的逐图结果, 耗时秒）。"""
    conditions = build_conditions()
    outcomes: dict[str, list[ImageOutcome]] = {condition.id: [] for condition in conditions}
    started_at = time.monotonic()

    for image_index, sample in enumerate(samples):
        rgb = load_rgb(sample.path)
        actual = labels[sample.label]
        for tier_index, degradation in enumerate(conditions):
            # 每（档位, 图片）一套独立种子：可复现，也不受遍历顺序影响。
            rng = np.random.default_rng([seed, tier_index, image_index])
            degraded, _stats = apply_degradation(degradation, rgb, rng)
            outcomes[degradation.id].append(
                evaluate_image(detector, classifier, sample, actual, degraded)
            )
        if verbose and (image_index + 1) % 20 == 0:
            print(f"  进度 {image_index + 1}/{len(samples)} 张", flush=True)

    return outcomes, time.monotonic() - started_at


def print_tables(
    stats: dict[str, dict[str, Any]],
    gate_rows: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    gate_comparisons: list[dict[str, Any]],
) -> None:
    """打印三张表：总览、清晰度单门、与基线数字的逐项对照。"""
    headers = [
        "条件",
        "漏检",
        "sharp p50",
        "无门准确率",
        "无门召回",
        "门后覆盖",
        "门后准确率",
        "太糊",
        "太暗",
        "过曝",
    ]
    rows: list[list[str]] = []
    for condition_id in CONDITION_IDS:
        row = stats[condition_id]
        rows.append(
            [
                condition_id,
                f"{row['misses']}/{row['n']}",
                fmt(row["sharpness_p50"], 1),
                fmt(row["accuracy_no_gate"]),
                fmt(row["shedding_recall_no_gate"]),
                fmt(row["coverage"]),
                fmt(row["accuracy_gated"]),
                str(row["blocks"][REASON_TOO_BLURRY]),
                str(row["blocks"][REASON_TOO_DARK]),
                str(row["blocks"][REASON_OVEREXPOSED]),
            ]
        )
    print("\n=== 质量门总览（valid，分母为全部图片；漏检算错）===")
    print(format_table(headers, rows, right_columns=set(range(1, len(headers)))))

    gate_table = [
        [
            row["condition"],
            str(row["n"]),
            str(row["blocked"]),
            fmt(row["rate"]),
        ]
        for row in gate_rows
    ]
    print(f"\n=== 清晰度单门（T={MIN_SHARPNESS}）在「干净且判对」子集上的拦截率 ===")
    print(format_table(["条件", "参与张数", "拦下", "拦截率"], gate_table, {1, 2, 3}))

    metric_names = {
        "misses": "漏检数",
        "sharpness_p50": "sharp p50",
        "accuracy": "无门准确率",
        "shedding_recall": "无门召回",
        "sharpness_gate_block_rate": "单门拦截率",
    }
    compare_rows = [
        [
            row["condition"],
            metric_names.get(row["metric"], row["metric"]),
            fmt(row["expected"]),
            fmt(row["measured"]),
            fmt(row["delta"]),
            "一致" if row["consistent"] else "不一致",
        ]
        for row in comparisons + gate_comparisons
    ]
    print("\n=== 与基线数字对照（容差：比率 ±0.02、漏检 ±1 张、p50 相对 ±2%）===")
    print(format_table(["条件", "指标", "基线", "实测", "偏差", "判定"], compare_rows, {2, 3, 4}))
    inconsistent = [row for row in comparisons + gate_comparisons if not row["consistent"]]
    print(f"\n共 {len(comparisons) + len(gate_comparisons)} 项，不一致 {len(inconsistent)} 项")


def main() -> int:
    parser = argparse.ArgumentParser(description="C6 输入质量门的标定与验收")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="验证集 split 目录")
    parser.add_argument("--detector", default=DEFAULT_DETECTOR, help="检测模型 .onnx")
    parser.add_argument("--classifier", default=DEFAULT_CLASSIFIER, help="分类模型 .onnx")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 张，0 表示全量")
    parser.add_argument("--out", default=DEFAULT_OUT, help="JSON 输出路径")
    parser.add_argument("--json-only", action="store_true", help="只写 JSON，不打印表格")
    args = parser.parse_args()

    dataset_dir = resolve_input_path(args.dataset)
    detector_path = resolve_input_path(args.detector)
    classifier_path = resolve_input_path(args.classifier)
    out_path = resolve_output_path(args.out)
    started_at = time.monotonic()

    classifier = OnnxStateClassifier.from_path(classifier_path)
    labels = classifier.labels
    if POSITIVE_LABEL not in labels or NEGATIVE_LABEL not in labels:
        raise SystemExit(f"模型标签里没有 {NEGATIVE_LABEL}/{POSITIVE_LABEL}: {labels}")
    if classifier.input_size != MEASURE_SIZE:
        raise SystemExit(
            f"分类器输入边长 {classifier.input_size} 与质量门的 {MEASURE_SIZE} 不一致，阈值不可迁移"
        )

    detector = OnnxDetector.from_path(detector_path)
    samples = collect_valid_samples(dataset_dir, labels)
    if args.limit > 0:
        samples = samples[: args.limit]
    if not samples:
        raise SystemExit(f"没有可用图片: {dataset_dir}")

    counts = Counter(labels[sample.label] for sample in samples)
    if not args.json_only:
        print("=== C6 输入质量门标定 ===")
        print(f"数据集: {dataset_dir}（{len(samples)} 张：{dict(counts)}）")
        print(f"检测器: {detector_path}（{detector.name}）")
        print(f"分类器: {classifier_path}（{classifier.name}，{classifier.input_size}×{classifier.input_size}）")
        print(f"随机种子: {SEED}（固定，可复现）")
        print(f"条件: {len(CONDITION_IDS)} 档 {list(CONDITION_IDS)}")
        print(
            f"阈值: sharpness≥{MIN_SHARPNESS} / lightness≥{MIN_LIGHTNESS} / "
            f"saturated≤{MAX_SATURATED}，裁剪外扩 {CROP_PADDING:.0%}"
        )
        if args.limit > 0:
            print(f"⚠️ --limit {args.limit}：样本已截断，不能与基线表逐项对比")

    outcomes, elapsed = run(samples, labels, detector, classifier, SEED, not args.json_only)
    stats = {
        condition_id: summarize_condition(outcomes[condition_id])
        for condition_id in CONDITION_IDS
    }

    baseline = outcomes["baseline"]
    clean_names = {row.name for row in baseline if row.correct}
    gate_rows = summarize_sharpness_gate(outcomes, clean_names, MIN_SHARPNESS)
    comparisons = compare_with_expected(stats)
    gate_comparisons = compare_sharpness_gate(gate_rows)

    if not args.json_only:
        print_tables(stats, gate_rows, comparisons, gate_comparisons)

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": {
            "root": str(dataset_dir),
            "n": len(samples),
            "counts": dict(counts),
            "limit": args.limit,
        },
        "models": {
            "detector": str(detector_path),
            "detector_name": detector.name,
            "classifier": str(classifier_path),
            "classifier_name": classifier.name,
            "labels": list(labels),
            "input_size": classifier.input_size,
        },
        "settings": {
            "seed": SEED,
            "crop_padding": CROP_PADDING,
            "measure_size": MEASURE_SIZE,
            "saturated_level": SATURATED_LEVEL,
            "thresholds": {
                "min_sharpness": MIN_SHARPNESS,
                "min_lightness": MIN_LIGHTNESS,
                "max_saturated": MAX_SATURATED,
            },
            "conditions": list(CONDITION_IDS),
            "gate_order": [REASON_TOO_BLURRY, REASON_TOO_DARK, REASON_OVEREXPOSED],
            "positive_label": POSITIVE_LABEL,
            "no_gate_denominator": "全部图片，漏检算错",
            "gated_denominator": "过了门并给出结论的图片",
        },
        "conditions": {
            condition_id: {
                **stats[condition_id],
                "per_sample": [row.as_json() for row in outcomes[condition_id]],
            }
            for condition_id in CONDITION_IDS
        },
        "sharpness_gate": {
            "threshold": MIN_SHARPNESS,
            "clean_correct_n": len(clean_names),
            "note": "分母只算该档检测到的干净样本；未检测到的图没走到门，不算拦截",
            "rows": gate_rows,
            "expected": EXPECTED_SHARPNESS_GATE,
            "comparisons": gate_comparisons,
        },
        "comparison": {
            "expected": EXPECTED,
            "rows": comparisons,
            "consistent": all(row["consistent"] for row in comparisons + gate_comparisons),
            "tolerance": {
                "rate": RATE_TOLERANCE,
                "misses": MISS_TOLERANCE,
                "sharpness_p50_relative": P50_RELATIVE_TOLERANCE,
            },
        },
        "run": {
            "elapsed_seconds": round(elapsed, 1),
            "total_seconds": round(time.monotonic() - started_at, 1),
            "inferences": len(samples) * len(CONDITION_IDS),
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "opencv": cv2.__version__,
            },
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_only:
        print(f"已写入 {out_path}", file=sys.stderr)
    else:
        print(f"\n已写入 {out_path}（{report['run']['elapsed_seconds']} s，{report['run']['inferences']} 次推理）")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

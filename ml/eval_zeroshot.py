"""零样本基准：用 CLIP 直接在带标注的测试集上区分 normal / shedding。

用途：判断「这题能不能靠语义（文字描述）分开」。不训练、不改产品代码，
只输出一份对照指标写进 docs/spike-zeroshot.md。

用法：
    python ml/eval_zeroshot.py --dataset ml/datasets/gecko-state-v2 \
        --split test --model openai/clip-vit-base-patch32
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

CLASS_ORDER = ("normal", "shedding")

PROMPTS: dict[str, tuple[str, ...]] = {
    "normal": (
        "a photo of a leopard gecko with normal healthy skin",
        "a close-up photo of a gecko with smooth normal scales",
        "a leopard gecko in normal vivid coloration",
    ),
    "shedding": (
        "a photo of a leopard gecko shedding its skin",
        "a close-up photo of a gecko with whitish peeling skin",
        "a leopard gecko covered in white shedding skin flakes",
        "a gecko with dull opaque whitish skin about to shed",
    ),
}


@dataclass(frozen=True)
class Sample:
    path: pathlib.Path
    label: str


def collect(dataset_root: pathlib.Path, split: str) -> list[Sample]:
    samples: list[Sample] = []
    split_dir = dataset_root / split
    for label in CLASS_ORDER:
        class_dir = split_dir / label
        if not class_dir.is_dir():
            continue
        for path in sorted(class_dir.iterdir()):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                samples.append(Sample(path=path, label=label))
    return samples


def class_text_embeddings(
    model: CLIPModel, processor: CLIPProcessor, device: str
) -> torch.Tensor:
    """每个类别把多条提示词的文本向量取平均后归一化，形状 (num_classes, dim)。"""
    vectors = []
    for label in CLASS_ORDER:
        inputs = processor(text=list(PROMPTS[label]), return_tensors="pt", padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            # transformers 5.x 里 CLIPModel 的整体前向要求图文同时输入，
            # 因此直接走子模块 + 投影层，拿到与图像侧对齐的文本向量。
            pooled = model.text_model(**inputs).pooler_output
            emb = model.text_projection(pooled)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        vectors.append(emb.mean(dim=0))
    stacked = torch.stack(vectors)
    return stacked / stacked.norm(dim=-1, keepdim=True)


def image_embeddings(
    model: CLIPModel,
    processor: CLIPProcessor,
    device: str,
    samples: list[Sample],
    batch_size: int,
) -> torch.Tensor:
    vectors = []
    for start in range(0, len(samples), batch_size):
        batch = samples[start : start + batch_size]
        images = [Image.open(sample.path).convert("RGB") for sample in batch]
        inputs = processor(images=images, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(device)
        with torch.no_grad():
            pooled = model.vision_model(pixel_values=pixel_values).pooler_output
            emb = model.visual_projection(pooled)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        vectors.append(emb.cpu())
    return torch.cat(vectors)


def auc(scores: list[float], labels: list[int]) -> float:
    """Rank 统计法算 AUC，避免额外依赖 sklearn。labels: 1 = 正类。"""
    pairs = sorted(zip(scores, labels), key=lambda item: item[0])
    rank_sum = 0.0
    for index, (_, label) in enumerate(pairs, start=1):
        if label == 1:
            rank_sum += index
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def evaluate(scores: list[float], labels: list[int], threshold: float) -> dict[str, object]:
    tp = sum(1 for score, label in zip(scores, labels) if score >= threshold and label == 1)
    fp = sum(1 for score, label in zip(scores, labels) if score >= threshold and label == 0)
    fn = sum(1 for score, label in zip(scores, labels) if score < threshold and label == 1)
    tn = sum(1 for score, label in zip(scores, labels) if score < threshold and label == 0)
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "threshold": round(threshold, 3),
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def best_threshold(scores: list[float], labels: list[int]) -> tuple[float, dict[str, object]]:
    candidates = sorted({round(score, 3) for score in scores})
    best = (0.5, evaluate(scores, labels, 0.5))
    for candidate in candidates:
        result = evaluate(scores, labels, candidate)
        if float(result["accuracy"]) > float(best[1]["accuracy"]):  # type: ignore[arg-type]
            best = (candidate, result)
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="CLIP 零样本基准")
    parser.add_argument("--dataset", default="ml/datasets/gecko-state-v2")
    parser.add_argument("--split", default="test")
    parser.add_argument("--model", default="openai/clip-vit-base-patch32")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dataset_root = pathlib.Path(args.dataset)
    samples = collect(dataset_root, args.split)
    if not samples:
        raise SystemExit(f"没有找到图片: {dataset_root / args.split}")
    labels = [1 if sample.label == "shedding" else 0 for sample in samples]

    model = CLIPModel.from_pretrained(args.model).to(device).eval()
    processor = CLIPProcessor.from_pretrained(args.model)
    logit_scale = float(model.logit_scale.exp().item())

    text = class_text_embeddings(model, processor, device)
    images = image_embeddings(model, processor, device, samples, args.batch_size)

    logits = logit_scale * images @ text.T.cpu()
    probs = logits.softmax(dim=-1)
    shedding_index = CLASS_ORDER.index("shedding")
    scores = probs[:, shedding_index].tolist()

    report = {
        "model": args.model,
        "split": args.split,
        "dataset": str(dataset_root),
        "count": len(samples),
        "positives": sum(labels),
        "auc": round(auc(scores, labels), 4),
        "at_0.5": evaluate(scores, labels, 0.5),
    }
    threshold, at_best = best_threshold(scores, labels)
    report["best"] = at_best
    report["best"]["threshold"] = round(threshold, 3)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out_path}")


if __name__ == "__main__":
    main()

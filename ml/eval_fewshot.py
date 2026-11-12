"""CLIP 特征 + 少量标注的 few-shot 探针（原型分类器）。

回答的问题：如果零样本直接判不行，那么用 CLIP 特征 + 少量标注（few-shot）
能不能接近全量微调的 ResNet18？如果 20 张/类就能到 0.85+，
说明采数据的成本可以大幅下降。

用法：
    python ml/eval_fewshot.py --dataset ml/datasets/gecko-state-v2 \
        --shots 1,5,10,20 --repeats 5
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
from dataclasses import dataclass

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

CLASS_ORDER = ("normal", "shedding")


@dataclass(frozen=True)
class Sample:
    path: pathlib.Path
    label: int


def collect(dataset_root: pathlib.Path, split: str) -> list[Sample]:
    samples: list[Sample] = []
    for index, label in enumerate(CLASS_ORDER):
        class_dir = dataset_root / split / label
        if not class_dir.is_dir():
            continue
        for path in sorted(class_dir.iterdir()):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                samples.append(Sample(path=path, label=index))
    return samples


def embed(
    model: CLIPModel, processor: CLIPProcessor, device: str, samples: list[Sample], batch_size: int
) -> torch.Tensor:
    vectors = []
    for start in range(0, len(samples), batch_size):
        batch = samples[start : start + batch_size]
        images = [Image.open(sample.path).convert("RGB") for sample in batch]
        pixel_values = processor(images=images, return_tensors="pt")["pixel_values"].to(device)
        with torch.no_grad():
            pooled = model.vision_model(pixel_values=pixel_values).pooler_output
            emb = model.visual_projection(pooled)
        emb = emb / emb.norm(dim=-1, keepdim=True)
        vectors.append(emb.cpu())
    return torch.cat(vectors)


def prototype_predict(features: torch.Tensor, labels: torch.Tensor, query: torch.Tensor) -> torch.Tensor:
    """每类取样本特征均值作为原型，按余弦相似度分类。"""
    prototypes = torch.stack([features[labels == index].mean(dim=0) for index in range(len(CLASS_ORDER))])
    prototypes = prototypes / prototypes.norm(dim=-1, keepdim=True)
    sims = query @ prototypes.T
    return sims.argmax(dim=-1)


def main() -> None:
    parser = argparse.ArgumentParser(description="CLIP 特征 few-shot 探针")
    parser.add_argument("--dataset", default="ml/datasets/gecko-state-v2")
    parser.add_argument("--model", default="openai/clip-vit-base-patch32")
    parser.add_argument("--shots", default="1,5,10,20")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dataset_root = pathlib.Path(args.dataset)
    train = collect(dataset_root, "train")
    test = collect(dataset_root, "test")

    model = CLIPModel.from_pretrained(args.model).to(device).eval()
    processor = CLIPProcessor.from_pretrained(args.model)

    train_features = embed(model, processor, device, train, args.batch_size)
    train_labels = torch.tensor([sample.label for sample in train])
    test_features = embed(model, processor, device, test, args.batch_size)
    test_labels = torch.tensor([sample.label for sample in test])

    shot_list = [int(value) for value in args.shots.split(",") if value.strip()]
    results = []
    rng = random.Random(args.seed)
    for shots in shot_list:
        accs: list[float] = []
        recalls: list[float] = []
        for _ in range(args.repeats):
            picked: list[int] = []
            for label in range(len(CLASS_ORDER)):
                indices = torch.nonzero(train_labels == label).flatten().tolist()
                picked.extend(rng.sample(indices, min(shots, len(indices))))
            subset = torch.tensor(picked)
            predictions = prototype_predict(train_features[subset], train_labels[subset], test_features)
            correctness = (predictions == test_labels)
            accs.append(float(correctness.float().mean()))
            shedding_mask = test_labels == CLASS_ORDER.index("shedding")
            recalls.append(float(correctness[shedding_mask].float().mean()))
        results.append(
            {
                "shots_per_class": shots,
                "accuracy_mean": round(sum(accs) / len(accs), 4),
                "accuracy_best": round(max(accs), 4),
                "shedding_recall_mean": round(sum(recalls) / len(recalls), 4),
                "repeats": args.repeats,
            }
        )

    report = {
        "model": args.model,
        "dataset": str(dataset_root),
        "train_size": len(train),
        "test_size": len(test),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out_path}")


if __name__ == "__main__":
    main()

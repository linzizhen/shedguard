"""训练蜕皮状态分类器，并导出服务端可直接加载的 ONNX。

输入是 `build_state_dataset.py` 产出的裁剪数据集，输出是：
- `ml/runs/<name>/weights/best.pt`：验证集准确率最高的权重
- `ml/models/<name>.onnx`：给 `SHEDGUARD_STATE_MODEL` 用
- `ml/models/<name>.labels.json`：类别顺序与输入尺寸，服务端从它读类别
- `ml/runs/<name>/summary.json`：测试集指标与训练参数，便于复现

注意 `labels.json` 必须与 ONNX 一起放：服务端不硬编码类别，换二态/三态模型只换文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_ROOT = PROJECT_ROOT / "ml" / "datasets" / "gecko-state"
RUNS_DIR = PROJECT_ROOT / "ml" / "runs"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
SEED = 42
OPTSET = 17


class CropDataset(Dataset[tuple[torch.Tensor, int]]):
    """按 `labels.json` 给定的类别顺序读取 `<split>/<class>/*.jpg`。"""

    def __init__(self, items: list[tuple[Path, int]], transform: Any) -> None:
        self._items = items
        self._transform = transform

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        path, label = self._items[index]
        with Image.open(path) as handle:
            image = handle.convert("RGB")
        return self._transform(image), label


def read_labels() -> tuple[str, ...]:
    payload = json.loads((DATASET_ROOT / "labels.json").read_text(encoding="utf-8"))
    labels = tuple(str(item) for item in payload["labels"])
    if len(labels) < 2:
        raise SystemExit(f"类别数不足，至少需要两个状态: {labels}")
    return labels


def collect(split: str, labels: tuple[str, ...]) -> list[tuple[Path, int]]:
    items: list[tuple[Path, int]] = []
    for index, name in enumerate(labels):
        for path in sorted((DATASET_ROOT / split / name).glob("*.jpg")):
            items.append((path, index))
    return items


def build_transforms(imgsz: int) -> tuple[Any, Any]:
    normalize = transforms.Normalize(
        mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)
    )
    train_transform = transforms.Compose(
        [
            transforms.RandomResizedCrop(imgsz, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2),
            transforms.ToTensor(),
            normalize,
        ]
    )
    # 服务端只做 resize + 归一化，没有中心裁剪，所以评估也必须 Resize 到整图。
    eval_transform = transforms.Compose(
        [
            transforms.Resize((imgsz, imgsz)),
            transforms.ToTensor(),
            normalize,
        ]
    )
    return train_transform, eval_transform


def build_model(arch: str, class_count: int) -> nn.Module:
    if arch == "resnet18":
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        model.fc = nn.Linear(model.fc.in_features, class_count)
        return model
    if arch == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(
            weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
        )
        in_features = model.classifier[3].in_features  # type: ignore[union-attr]
        model.classifier[3] = nn.Linear(in_features, class_count)  # type: ignore[index]
        return model
    raise SystemExit(f"不支持的骨干网络: {arch}")


def class_weights(items: list[tuple[Path, int]], class_count: int) -> torch.Tensor:
    counts = np.zeros(class_count, dtype=np.float64)
    for _, label in items:
        counts[label] += 1
    counts = np.maximum(counts, 1.0)
    weights = counts.sum() / (class_count * counts)
    return torch.tensor(weights, dtype=torch.float32)


def evaluate(
    model: nn.Module,
    loader: DataLoader[tuple[torch.Tensor, int]],
    device: torch.device,
    class_count: int,
) -> tuple[float, np.ndarray]:
    model.eval()
    confusion = np.zeros((class_count, class_count), dtype=np.int64)
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            predictions = model(images).argmax(dim=1).cpu().numpy()
            truths = labels.numpy()
            for truth, predicted in zip(truths, predictions, strict=True):
                confusion[int(truth), int(predicted)] += 1
            correct += int((predictions == truths).sum())
            total += len(truths)
    accuracy = correct / total if total else 0.0
    return accuracy, confusion


def summarize(confusion: np.ndarray, labels: tuple[str, ...]) -> dict[str, Any]:
    per_class: dict[str, Any] = {}
    for index, name in enumerate(labels):
        true_positive = int(confusion[index, index])
        predicted = int(confusion[:, index].sum())
        actual = int(confusion[index, :].sum())
        per_class[name] = {
            "precision": round(true_positive / predicted, 4) if predicted else None,
            "recall": round(true_positive / actual, 4) if actual else None,
            "support": actual,
        }
    return {
        "per_class": per_class,
        "confusion": confusion.tolist(),
    }


def export_onnx(model: nn.Module, imgsz: int, target: Path) -> None:
    model.eval().cpu()
    dummy = torch.randn(1, 3, imgsz, imgsz)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        target.as_posix(),
        input_names=["input"],
        output_names=["logits"],
        opset_version=OPTSET,
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
    )
    inline_external_data(target)


def inline_external_data(target: Path) -> None:
    """把外部权重并回单个 .onnx。

    torch 的导出器会把权重写成同名的 `.onnx.data`，服务端就得管两个文件，
    而且它还会在临时目录里留下删不掉的残骸。重新保存一次即可自包含。
    """
    import onnx

    data_file = target.with_name(f"{target.name}.data")
    if data_file.is_file():
        proto = onnx.load(target.as_posix())
        onnx.save(proto, target.as_posix())
        data_file.unlink(missing_ok=True)

    for leftover in MODELS_DIR.glob(f".{target.name}.data.*"):
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练蜕皮状态分类器")
    parser.add_argument(
        "--arch", default="resnet18", choices=["resnet18", "mobilenet_v3_small"]
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--name", default="gecko-state")
    parser.add_argument(
        "--dataset",
        default=str(DATASET_ROOT),
        help="数据集根目录（含 labels.json 与 train/valid/test），默认 ml/datasets/gecko-state",
    )
    parser.add_argument("--device", default="", help="留空自动选择；也可显式指定 cpu / 0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global DATASET_ROOT
    DATASET_ROOT = Path(args.dataset)
    if not (DATASET_ROOT / "labels.json").is_file():
        raise SystemExit(f"数据集不存在: {DATASET_ROOT}，先跑 ml/build_state_dataset.py")

    torch.manual_seed(SEED)
    labels = read_labels()
    class_count = len(labels)

    train_items = collect("train", labels)
    valid_items = collect("valid", labels)
    test_items = collect("test", labels)
    if not train_items or not test_items:
        raise SystemExit("训练集或测试集为空")

    device = torch.device(
        args.device
        if args.device
        else ("cuda" if torch.cuda.is_available() else "cpu")
    )
    train_transform, eval_transform = build_transforms(args.imgsz)
    train_loader = DataLoader(
        CropDataset(train_items, train_transform),
        batch_size=args.batch,
        shuffle=True,
        num_workers=0,
    )
    valid_loader = DataLoader(
        CropDataset(valid_items, eval_transform),
        batch_size=args.batch,
        num_workers=0,
    )
    test_loader = DataLoader(
        CropDataset(test_items, eval_transform),
        batch_size=args.batch,
        num_workers=0,
    )

    model = build_model(args.arch, class_count).to(device)

    criterion = nn.CrossEntropyLoss(weight=class_weights(train_items, class_count).to(device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    run_dir = RUNS_DIR / args.name
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    best_path = weights_dir / "best.pt"
    best_accuracy = 0.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for images, labels_batch in train_loader:
            images = images.to(device)
            labels_batch = labels_batch.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels_batch)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * len(labels_batch)
        scheduler.step()

        valid_accuracy, _ = evaluate(model, valid_loader, device, class_count)
        average_loss = running_loss / len(train_items)
        print(
            f"epoch {epoch}/{args.epochs} loss {average_loss:.4f} valid_acc {valid_accuracy:.4f}",
            flush=True,
        )
        if valid_accuracy >= best_accuracy:
            best_accuracy = valid_accuracy
            torch.save(model.state_dict(), best_path)

    if not best_path.is_file():
        raise SystemExit(f"训练未产出权重: {best_path}")

    model.load_state_dict(torch.load(best_path, map_location=device))
    test_accuracy, confusion = evaluate(model, test_loader, device, class_count)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODELS_DIR / f"{args.name}.onnx"
    export_onnx(model, args.imgsz, onnx_path)

    labels_payload = {"labels": list(labels), "input_size": args.imgsz}
    labels_path = MODELS_DIR / f"{args.name}.labels.json"
    labels_path.write_text(json.dumps(labels_payload, indent=2), encoding="utf-8")

    summary = {
        "name": args.name,
        "arch": args.arch,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "lr": args.lr,
        "seed": SEED,
        "device": str(device),
        "labels": list(labels),
        "sizes": {
            "train": len(train_items),
            "valid": len(valid_items),
            "test": len(test_items),
        },
        "best_valid_accuracy": round(best_accuracy, 4),
        "test": {"accuracy": round(test_accuracy, 4), **summarize(confusion, labels)},
        "weights": best_path.as_posix(),
        "onnx": onnx_path.as_posix(),
        "onnx_bytes": onnx_path.stat().st_size,
        "labels_file": labels_path.as_posix(),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ml

蜕皮识别的离线部分：把公开标注数据整理成可训练的数据集，训出「守宫在哪」的检测器，导出服务端能加载的 ONNX。

## 为什么只训「守宫在哪」

公开数据 `capstone-habql/gecko_1`（1,163 张）有三个类别：`gecko`、`gecko-shedding`、`gecko-abnormal`。后两个是**状态**标签，不是物体标签，而且分布有严重偏差：

- 短边 < 400px 的图占 90.9%，且其中绝大多数是网络图库缩略图；
- 蜕皮标注几乎全部落在高分辨率摄影棚微距图上（蜕皮组平均 451,295 像素，非蜕皮组 69,863 像素）；
- 直接训三分类，模型会学到「白背景 + 高清 = 蜕皮」，而不是「体表变白 = 蜕皮」。

所以数据集只保留 `gecko` 类，任务收敛成单类别检测。蜕皮判断交给 `server/` 的信号层与时序层，那里不依赖这批数据。

## 构建数据集

```powershell
# 在仓库根目录
.\.venv\Scripts\python.exe ml\prepare_detection_dataset.py
```

输入 `data/raw/gecko1/`（YOLOv8 分割格式），输出 `ml/datasets/gecko-det/`：

- 分割多边形转成外接矩形框；
- 只保留 `gecko` 类，蜕皮与异常标注行丢弃；
- 面积占比 < 1% 或短边 < 24px 的框丢弃（这些框在 640 输入下会缩到不足 2 像素）；
- 没有合法框的图整张丢弃。

本次结果：1,120 图 / 1,124 框，丢弃 43 张（都是只标了蜕皮、没标守宫本体的图），面积占比中位数 0.53。产物里有 `stats.json` 记录这些数字与 `dataset_hash`。

## 训练

```powershell
.\.venv\Scripts\python.exe ml\train_detector.py --epochs 50 --batch 16
```

产物：

| 路径 | 说明 |
|---|---|
| `ml/runs/gecko-det/weights/best.pt` | 训练权重 |
| `ml/models/gecko-det.onnx` | 给服务端加载，配 `SHEDGUARD_DETECTOR_MODEL` |
| `ml/runs/gecko-det/summary.json` | 测试集 precision / recall / mAP 与训练参数 |

验收线：`mAP50 ≥ 0.85`。单类别、构图简单，低于这个值优先怀疑数据转换而不是模型。

`ml/datasets/`、`ml/runs/`、`*.onnx`、`*.pt` 都在 `.gitignore` 里，不进仓库。

## 已知限制

- 训练数据全是可见光，**没有一张红外夜拍图**。装到真机上很可能要用手工标注的几十张真实红外图微调，这是当前最大的未知。
- 物种不纯：数据里有高冠变色龙、豹纹变色龙、安乐蜥、鬃狮蜥，不只是豹纹守宫。对「找到爬宠身体」这个任务是好事（泛化更强），对「豹纹守宫体表特征」没有帮助。
- 数据来自网络，构图、背景、光照与固定机位差异很大。检测框会偏松，信号层的 10% 内缩就是为这种宽松框准备的。
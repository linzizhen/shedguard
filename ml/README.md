# ml

蜕皮识别的离线部分。这里训两个模型，它们职责不同、可以各自独立迭代：

| 模型 | 任务 | 产物 | 服务端配置 |
|---|---|---|---|
| 检测器 | 守宫在画面里的哪个位置 | `ml/models/gecko-det.onnx` | `SHEDGUARD_DETECTOR_MODEL` |
| 状态分类器 | 裁剪出的守宫处于哪个蜕皮阶段 | `ml/models/gecko-state.onnx` + `.labels.json` | `SHEDGUARD_STATE_MODEL` |

分开训的理由：状态定义会反复调整（先是「蜕皮中」，后来加了「蒙白」，将来可能还要分「卡皮」），而「守宫在哪」这个任务半年不用动。捆在一个模型里，每改一次状态定义就要重训一次检测器。

## 检测器：为什么只训「守宫在哪」

公开数据 `capstone-habql/gecko_1`（1,163 张）有三个类别：`gecko`、`gecko-shedding`、`gecko-abnormal`。后两个是**状态**标签，不是物体标签，而且分布有严重偏差：

- 短边 < 400px 的图占 90.9%，且其中绝大多数是网络图库缩略图；
- 蜕皮标注几乎全部落在高分辨率摄影棚微距图上（蜕皮组平均 451,295 像素，非蜕皮组 69,863 像素）；
- 直接训三分类，模型会学到「白背景 + 高清 = 蜕皮」，而不是「体表变白 = 蜕皮」。

所以检测器只保留 `gecko` 类，任务收敛成单类别检测。状态判断交给下游的分类器与 `server/` 的信号层。

## 安装依赖

训练依赖与服务端分开：`ml/requirements.txt` 有 torch、torchvision、ultralytics，体积大、有 GPU 绑定，不进服务端部署。服务端只装 `server/requirements.lock`。

```powershell
# 在仓库根目录
.\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
```

训练走 GPU 时要注意：PyPI 上的 Windows `torch` 是**纯 CPU 版**（版本号带 `+cpu`，`torch.cuda.is_available()` 返回 `False`）。必须从 PyTorch 官方源装 CUDA 版：

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cu130 `
    "torch==2.14.1+cu130" "torchvision==0.29.1+cu130"
```

`cu130` 通道当前最高只到 `torch 2.14.1`，比 PyPI 的 `2.15.0` 低一个次要版本，`ultralytics` 兼容。wheel 约 2.5 GB，装之前先确认磁盘与网络。

`ultralytics` 会连带装 `opencv-python`（带 GUI 版），覆盖服务端要的 `opencv-python-headless`。两者提供同一个 `cv2` 模块，服务端只用到 `imdecode`/`cvtColor`，功能不受影响。

## 检测器：构建数据集

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

## 检测器：训练

```powershell
# 训练进程会用 multiprocessing 建命名管道，DSH 沙箱的 workspace-write 模式下
# 会报 PermissionError: [WinError 5]，必须以完整权限运行。
$env:MPLCONFIGDIR=".tmp\mpl"                 # 默认写到 C:\Users\...\.matplotlib，沙箱只读
$env:YOLO_CONFIG_DIR=".tmp\ultralytics"
$env:TEMP=".tmp"; $env:TMP=".tmp"

.\.venv\Scripts\python.exe ml\train_detector.py --epochs 50 --batch 16
```
产物：

| 路径 | 说明 |
|---|---|
| `ml/runs/gecko-det/weights/best.pt` | 训练权重 |
| `ml/models/gecko-det.onnx` | 给服务端加载，配 `SHEDGUARD_DETECTOR_MODEL` |
| `ml/runs/gecko-det/summary.json` | 测试集 precision / recall / mAP 与训练参数 |

验收线：`mAP50 ≥ 0.85`。单类别、构图简单，低于这个值优先怀疑数据转换而不是模型。

`ml/datasets/`、`ml/runs/`、`*.onnx`、`*.pt` 都在 `.gitignore` 里，不进仓库。模型不入库是因为重训只要几分钟，而 12 MB 的二进制文件放进 Git 只会拖慢克隆。

## 检测器：训练结果（2026-11-02）

RTX 5070 上 50 个 epoch 用了 **3.6 分钟**，`yolov8n.pt` 微调，`imgsz=640`、`batch=16`、`seed=42`、`patience=20`，实际跑满 50 轮未触发早停。

| 划分 | 图片 | 实例 | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|---|---|
| valid | 349 | 350 | 0.912 | 0.914 | 0.946 | 0.586 |
| test | 112 | 114 | 0.850 | 0.868 | **0.902** | 0.578 |

测试集 `mAP50 = 0.902`，通过验收线。导出 ONNX 12.2 MB，服务端 `OnnxDetector` 直接加载，拿测试集真图跑 8 张全部检出（置信度 0.63–0.92，框面积占比 0.15–0.85）。

valid 比 test 高 4.4 个点。数据只有 1,120 张、来源又杂，这个差距在噪声范围内，但还是说明**未见过的构图会掉点**——真实机位下会掉得更多，因为一张红外图都没训过。

## 状态分类器：构建数据集

```powershell
# 在仓库根目录
.\.venv\Scripts\python.exe ml\build_state_dataset.py
```

输入同样是 `data/raw/gecko1/`，输出 `ml/datasets/gecko-state/{train,valid,test}/{normal,shedding}/`。

标签规则：图里有 `gecko` 框、没有 `gecko-shedding` 框 → `normal`；两者都有 → `shedding`；只有蜕皮框没有本体框 → 丢弃（定位不到本体，裁不出图）。裁剪取面积最大的 `gecko` 框并外扩 8%，短边 < 24px 的丢弃。

本次结果：`normal` 845 张、`shedding` 275 张（train 507/152、valid 258/91、test 80/32），丢弃 43 张。产物 `labels.json` 记录类别顺序与输入尺寸——**服务端从它读类别，不硬编码**。

## 状态分类器：训练

```powershell
$env:TORCH_HOME=".tmp\torch"      # 权重缓存放仓库内，避免写用户目录被沙箱拒绝
$env:TEMP=".tmp"; $env:TMP=".tmp"

.\.venv\Scripts\python.exe ml\train_state_classifier.py --arch resnet18 --epochs 15
```

`--arch` 支持 `resnet18`（45 MB ONNX，当前默认）与 `mobilenet_v3_small`（约 10 MB，精度略低）。训练用类别频率加权交叉熵（`shedding` 权重约为 `normal` 的 2 倍），评估只做 `Resize` 不做中心裁剪——服务端也是整图缩放，两边必须一致。

导出后会自动把 torch 写出的 `.onnx.data` 内联回单个 `.onnx`，服务端只需管一个文件。

## 状态分类器：训练结果（2026-11-04）

RTX 5070 上 15 个 epoch 约 2 分钟，`resnet18` ImageNet 预训练微调，`imgsz=224`、`batch=32`、`lr=1e-3`、`seed=42`、余弦退火。

| 指标 | 数值 |
|---|---|
| 验证集最好准确率 | 0.9255 |
| 测试集准确率 | 0.9107 |
| `normal` | precision 0.9167 / recall 0.9625（80 张） |
| `shedding` | precision 0.8929 / recall 0.7812（32 张） |

早前用简单增强跑的一次探路是 93.75%，这里低 2.7 点——训练配置不同（加了 `RandomResizedCrop`、颜色抖动与余弦退火），不是同一条件下的退化。没有针对这批数据继续调参：它本来就不是产品数据，调出来的数字没有意义。

服务端集成验证：`OnnxStateClassifier.from_path` 直接加载 44.8 MB 的 `gecko-state.onnx`，真图端到端冒烟里 5 张蜕皮图 4 张判对（置信度 0.997–1.0），1 张置信度 0.513 被降级为 `unknown`，3 张正常图全对。

## 状态分类器：并入网络复核数据（gecko-state-v2，2026-11-11）

把 `docs/data-search-2026-11-09.md` 记录的 343 张网络图逐张复核后，挑出可信的并入训练集，产出 `gecko-state-v2` 并重训，验证「加网络数据到底有没有用」。整条链路是四个脚本：

```powershell
# 1) 跑检测器裁剪 + 自动打标 + dHash（产物在 data/collected_crops/，已 gitignore）
$env:PYTHONPATH="server\src"
.\.venv\Scripts\python.exe ml\curate_collected.py
# 2) 近重复聚类 + 生成拼图 data/collected_crops/sheets/sheet_XX.jpg 供人工看
.\.venv\Scripts\python.exe ml\dedup_collected.py
# 3) 人工逐张判定写进 data/collected_crops/review.csv
.\.venv\Scripts\python.exe ml\review_collected.py
# 4) 只把复核通过的并入 train，测试集保持原样，产出 gecko-state-v2
.\.venv\Scripts\python.exe ml\build_state_dataset_v2.py
# 5) 用 --dataset 指向 v2 重训
.\.venv\Scripts\python.exe ml\train_state_classifier.py --name gecko-state-v2 --dataset ml\datasets\gecko-state-v2 --epochs 15
```

**复核结论（关键事实）**：343 张 → 近重复聚类 325 簇 → 人工只留下 **88 张（normal 68 + shedding 20）**，其余 237 簇丢弃。丢弃主因是物种不对：搜狗那批绝大多数是**睫角守宫、肥尾守宫、睑虎、壁虎科野生种**，以及只有皮屑的特写、远景小目标、空箱/空手、卡通字幕遮挡；还有一批全身奶白无法区分「白化/暴雪基因」与「蒙白」，为不污染类别一律丢弃（这也是 opaque 类仍为零的原因）。

**A/B 对比（测试集均为原始 gecko1 的 80 normal / 32 shedding，未掺入任何网络图）**：

| 指标 | v1（gecko1） | v2（gecko1 + 88 张复核图，只加 train） |
|---|---|---|
| 测试集准确率 | 0.9107 | **0.9286** |
| `normal` recall（80） | 0.9625 | 0.9750 |
| `shedding` recall（32） | 0.7812 | **0.8125** |
| 验证集最好准确率 | 0.9255 | 0.9427 |

净收益约 +1.8 个点，`shedding` 召回 +3.1 个点，且没有拖累 `normal`。提升不大是因为真正干净可用的新图只有 88 张——网络数据量看着大，能用的是少数。**结论：v2 在留出测试集上优于 v1，部署时把 `SHEDGUARD_STATE_MODEL` 指向 `ml/models/gecko-state-v2.onnx` 即可**（两个模型文件都在 `ml/models/`，`labels.json` 同名，服务端不硬编码类别）。

## 状态分类器：Bing 扩图与 v3（2026-11-13，未部署）

为了回答「再多一点图能不能提升召回」，用 Bing 图片搜索又拉了一批：

```powershell
# 1) 抓图（Bing 异步接口，8 组中英文查询 × 4 页），产物在 data/collected/bing_*/
#    脚本在 .tmp 里，未入库；元数据落 data/collected/_bing_meta.csv
# 2) 重新裁剪 + 自动打标（同 v2 第 1 步）
$env:PYTHONPATH="server\src"
.\.venv\Scripts\python.exe ml\curate_collected.py
# 3) 用置信度硬门控并入 train，产出 gecko-state-v3
.\.venv\Scripts\python.exe ml\build_state_dataset_v3.py
# 4) 重训
.\.venv\Scripts\python.exe ml\train_state_classifier.py --name gecko-state-v3 --dataset ml\datasets\gecko-state-v3 --epochs 15
# 5) 按 p(shedding) 扫阈值，对比两个模型的实际工作点
.\.venv\Scripts\python.exe ml\eval_state_thresholds.py
```

**采集与清洗**：元数据 1052 条 → 下载 512 张 → 人工删掉 50 张（重复图、睫角守宫、AI 图、视频封面）→ 再移出 22 张（3D 打印模型、陶土雕塑、扭蛋摆件、游戏截图、图文海报、只有蜕下的皮）→ 剩 **436 张**。

**v3 的标签规则**：不再人工逐张判定，而是用 v1 分类器的概率做硬门控——`p(shedding) ≥ 0.85` 记 shedding、`≤ 0.25` 记 normal，中间灰区（104 张）直接丢掉。最终并入 train **normal 52 / shedding 246**（另有 34 张与现有图 dHash 近重复被剔除），valid/test 原样不动。

**A/B 与阈值扫描（测试集仍为原始 gecko1 的 80 normal / 32 shedding）**：

| 模型 / 阈值 | 测试准确率 | 蜕皮召回 | 蜕皮精确率 | FP / FN |
|---|---|---|---|---|
| v2 @ argmax | 0.9286 | 0.8125 | 0.9286 | 2 / 6 |
| v2 @ p≥0.80 | **0.9464** | 0.8438 | **0.9643** | 1 / 5 |
| v3 @ argmax(0.5) | 0.9018 | **0.9062** | 0.7838 | 8 / 3 |
| v3 @ p≥0.80 | 0.9018 | 0.7812 | 0.8621 | 4 / 7 |

**结论：v3 不部署。** 用弱模型（v1）的预测当新数据的标签，等于把 v1 的判断误差直接写进训练集——召回是上去了（0.8125 → 0.9062），但精确率掉到 0.78，意味着正常日里约每 10 天就有 1 天误报。v2 那 88 张是人工逐张看的，虽然少，但标签干净。

**顺带得到的可用结论（阈值）**：v2 在 `p(shedding) ≥ 0.80` 时测试准确率 0.9464、精确率 0.9643 都优于默认 argmax，说明「提醒线」比「分类 argmax」更适合往上提一点。但 P22 已证明模糊越重置信度越高，这条规则在退化图上传不住，所以**暂不改服务端默认值**，等真实机位数据再定（见 `docs/plan.md` §7）。

## 已知限制

这些限制对两个模型都成立：

- 训练数据全是可见光，**没有一张红外夜拍图**。装到真机上很可能要用手工标注的几十张真实红外图微调，这是当前最大的未知。
- 物种不纯：数据里有高冠变色龙、豹纹变色龙、安乐蜥、鬃狮蜥，不只是豹纹守宫。对「找到爬宠身体」这个任务是好事（泛化更强），对「豹纹守宫体表特征」没有帮助。
- 数据来自网络，构图、背景、光照与固定机位差异很大。检测框会偏松，信号层的 10% 内缩就是为这种宽松框准备的。

状态分类器额外的问题：

- **蒙白类样本为零**。`gecko-shedding` 标注全是「皮正在掉」的瞬间，没有一张是静止蒙白态。所以现在只能跑二态，而产品真正需要的是蒙白预警——这是整个识别链路最大的缺口。
- 标注语义不纯：漏报的样本里有一张是「绿鬣蜥尾巴缠绷带、残留旧皮」的伤口照，说明这个数据集混进了医疗案例。
- 浅色基因（白化、暴风雪）在红外下是否还能看出蒙白，没有任何资料可依。
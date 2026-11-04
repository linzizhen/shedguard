# 蜕皮状态识别设计规格

> 状态：草案，待评审
> 前置：`docs/spike-shedding-state.md`（探路结论：状态可分，但现有数据不可直接用于产品）
> 相关：`docs/specs/2026-11-02-shed-detection-core-design.md`（三层架构）、`2026-11-02-shed-judgement-design.md`（时序判定）

## 1. 背景与目标

原设计走「时序预测」：用体表指标的个体基线推断蜕皮将至。该路线要求同一只守宫 2–3 个月的连续影像，而项目目前一张真实饲养箱照片都没有，阈值无法校准。

本规格改为「状态识别」：直接判断**当前这一帧**守宫处于蜕皮的哪个阶段。它不预测未来，只报告现在。

探路已验证：正常与蜕皮中在图像上可分（测试集 93.75%）。但探路数据集物种混杂、无红外、无蒙白样本，因此本规格的模型**明确标注为未经真实数据验证**，管线按最终形态实现，模型待自采数据到位后重训。

### 目标

- 对任意一张已入库图片，输出蜕皮状态与置信度
- 按设备与日期聚合，推导「蜕皮开始」与「蜕皮完成」事件
- 模型缺失或不可用时明确降级，不静默返回错误结论

### 非目标

- 不预测未来若干天后是否蜕皮（那是 M6 的职责，保留但不作为主路径）
- 不自动写入 `shed_events`（事实层由用户确认）
- 不区分蜕皮是否顺利（卡皮判定需要更细的部位级信息）

## 2. 状态与事件定义

### 2.1 视觉状态（模型输出）

| 状态 | 含义 | 视觉特征 |
|---|---|---|
| `normal` | 无蜕皮迹象 | 皮肤纹理清晰、图案对比度正常 |
| `opaque` | 蒙白 | 全身或大面积均匀发白/发灰，图案对比度显著下降，皮尚未脱落 |
| `shedding` | 蜕皮中 | 可见皮屑掀起、剥落，新旧皮肤交界明显 |
| `unknown` | 无法判断 | 未检出守宫、分类置信度低于阈值、或模型不可用 |

`unknown` 不是模型类别，是服务层的判定结果。

### 2.2 事件（服务层由状态转换推导）

| 事件 | 触发条件 |
|---|---|
| `shed_started` | 前一有效日为 `normal` 或不存在，当日为 `opaque` 或 `shedding` |
| `shed_completed` | 前一有效日为 `opaque` 或 `shedding`，当日为 `normal` |

**「已蜕完」不是视觉状态**：皮掉完之后守宫恢复常态，与从未蜕皮在单帧上不可区分。它只能由转换推导。

### 2.3 每日状态聚合

一天内可能有多次拍摄。每日状态按当天所有已分析图片投票：

1. `unknown` 不参与投票。
2. 取众数。
3. 平票时按 `shedding > opaque > normal` 取优先级——漏报蜕皮的代价高于误报，宁可让用户多看一眼。
4. 当天无任何有效图 → 该日**无状态**，不是 `normal`。这与 M6 的 `insufficient` 语义一致。

## 3. 架构

```
POST /api/v1/shedding/{image_id}
  1. 取原图（复用 ImageRepository + Storage）
  2. OnnxDetector 定位守宫（复用 M4）
  3. 裁剪守宫框 + padding → 224×224
  4. OnnxStateClassifier 三态分类
  5. 置信度 < SHEDGUARD_STATE_MIN_CONFIDENCE → unknown
  6. 落 shedding_states 表
```

分层位置：

| 层 | 新增内容 |
|---|---|
| `domain` | `ShedState` 枚举、`StatePrediction`、`StateClassifier` Protocol、事件推导纯函数 |
| `services` | `SheddingService`：编排取图 → 检测 → 裁剪 → 分类 → 落库；`series` 聚合与事件推导 |
| `infra` | `OnnxStateClassifier`（onnxruntime）、`classifier.py` |
| `api` | `routes/shedding.py`、依赖注入 |
| `migrations` | `0004_shedding_states` |

分类器通过 Protocol 抽象，与 `Detector` 同一模式，测试用 `FakeClassifier` 注入。

## 4. 数据契约与训练

### 4.1 数据集构建

新增 `ml/build_state_dataset.py`：

- 输入：`data/raw/gecko1/`（现有标注）与 `data/raw/opaque/`（蒙白，待补）
- 标签规则：
  - 有 `gecko` 框、无 `shedding` 框 → `normal`
  - 有 `gecko` 框、有 `shedding` 框 → `shedding`
  - `data/raw/opaque/` 下的图 → `opaque`
- 裁剪：面积最大的 `gecko` 框外扩 `--padding`（默认 0.08），短边 < 24 px 丢弃
- 输出：`ml/datasets/gecko-state/{train,valid,test}/{class}/`、`stats.json`、`labels.json`
- 缺少 `opaque` 目录时按二态构建，并在 `stats.json` 标注 `classes: ["normal", "shedding"]`

### 4.2 训练

新增 `ml/train_state_classifier.py`：

- `--arch` 支持 `resnet18`（默认）与 `mobilenet_v3_small`
- 224×224、AdamW、余弦退火、按类别频率加权交叉熵
- 导出 ONNX（opset 17），同时写 `<name>.labels.json` 记录类别顺序
- 评估输出混淆矩阵与逐类 precision/recall，写入 `ml/runs/<name>/summary.json`

**类别顺序必须随模型走**：服务端从 `labels.json` 读取类别，不能硬编码三态。这样二态模型与三态模型可以共存，等蒙白数据到位后直接换模型文件。

### 4.3 模型产物

- `ml/models/gecko-state.onnx`（不进仓库）
- `ml/models/gecko-state.labels.json`

## 5. 服务层接口

### 5.1 单图状态

```
POST /api/v1/shedding/{image_id}
```

成功 `200`：

```json
{
  "image_id": "01J...",
  "local_date": "2026-11-04",
  "state": "opaque",
  "confidence": 0.8712,
  "probabilities": {"normal": 0.0521, "opaque": 0.8712, "shedding": 0.0767},
  "detection": {"box": {"x1": 120, "y1": 88, "x2": 402, "y2": 311}, "confidence": 0.9134},
  "classifier_name": "onnx:gecko-state",
  "computed_at_utc": "2026-11-04T08:12:33Z"
}
```

- 未检出守宫：`state` 为 `unknown`，`probabilities` 与 `detection` 为 `null`
- 重复调用幂等：`(image_id, classifier_name)` 已存在时直接返回既有结果
- 模型未配置：`503 MODEL_UNAVAILABLE`

### 5.2 序列与事件

```
GET /api/v1/series/{device_id}/shedding?from=2026-11-01&to=2026-11-30
```

```json
{
  "device_id": "cam-1",
  "from": "2026-11-01",
  "to": "2026-11-30",
  "days": [
    {"date": "2026-11-01", "state": "normal", "votes": {"normal": 8, "shedding": 0, "opaque": 0}, "image_count": 8},
    {"date": "2026-11-02", "state": null, "votes": {}, "image_count": 0}
  ],
  "events": [
    {"type": "shed_started", "date": "2026-11-03", "previous": "normal", "current": "opaque"}
  ],
  "current_state": "opaque"
}
```

- 区间校验复用 `domain/judgement.py` 的 `validate_range`（倒序与超 366 天均返回 `400 INVALID_REQUEST`）
- `current_state` 取最后一个有状态的日期；全部无状态时为 `null`

## 6. 存储与迁移

新增表 `shedding_states`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `image_id` | TEXT PK | 外键 `images.id` |
| `state` | TEXT | `normal` / `opaque` / `shedding` / `unknown` |
| `confidence` | REAL | 最高类概率，`unknown` 时为 NULL |
| `probabilities_json` | TEXT | 完整概率分布 |
| `detector_name` | TEXT | 定位模型标识 |
| `classifier_name` | TEXT | 分类模型标识，含模型 stem |
| `box_json` | TEXT | 守宫框，未检出时 NULL |
| `computed_at_utc` | TEXT | ISO 8601 UTC |
| `state_version` | TEXT | 状态定义版本，便于重算 |

迁移 `0004_shedding_states`，`down_revision = "0003"`。

不新建事件表：事件由状态序列实时推导，落表会引入「状态变了事件没变」的一致性问题（与 M6 的取舍一致）。

## 7. 配置项

新增 3 项（18 → 21）：

| 变量 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| `SHEDGUARD_STATE_MODEL` | str | `""` | — | ONNX 路径，空表示不启用状态识别 |
| `SHEDGUARD_STATE_MIN_CONFIDENCE` | float | `0.6` | 0.0–1.0 | 低于此值判 `unknown` |
| `SHEDGUARD_STATE_CROP_PADDING` | float | `0.08` | 0.0–0.3 | 裁剪守宫框时的外扩比例 |

模型文件缺失或加载失败时，`/readyz` 返回非就绪并说明原因（与 `detector_error` 同一模式）。

## 8. 验收标准

1. 对已入库图片调用 `POST /api/v1/shedding/{image_id}` 返回 200 与三态之一
2. 未检出守宫时返回 `state = "unknown"`，不写入伪造的 `normal`
3. 置信度低于阈值时返回 `unknown`，但 `probabilities` 仍完整返回
4. 同一 `image_id` 重复调用结果与 `computed_at_utc` 不变
5. 模型未配置时返回 `503 MODEL_UNAVAILABLE`，且 `/readyz` 报告未就绪
6. 每日状态按众数聚合，平票按 `shedding > opaque > normal` 取
7. 当天无有效图时该日状态为 `null`，不是 `normal`
8. `normal → opaque` 产生 `shed_started`，`opaque → normal` 产生 `shed_completed`
9. 倒序区间与超过 366 天返回 `400 INVALID_REQUEST`
10. 分类器类别顺序从 `labels.json` 读取，二态模型与三态模型都能加载

## 9. 已知欠账

| 欠账 | 影响 | 计划 |
|---|---|---|
| 零蒙白训练数据 | 三态实际只能跑二态 | 自采补齐 |
| 未在红外图像上验证 | 产品场景可能完全失效 | Phase 2 数据到位后重训 |
| 训练数据物种混杂 | 可能学到非目标物种特征 | 按物种重新标注 |
| 无时序平滑 | 单帧抖动可能造成事件闪烁 | 已用当日投票缓解，仍需真实数据检验 |
| 浅色基因（白化、暴风雪）蒙白不可辨 | 这类个体可能永远判不出 `opaque` | 需单独评估，可能列为不支持 |
| 不区分卡皮 | 只能提示「在蜕皮」，不能提示「蜕不干净」 | 后续版本 |
| 无自动写入 `shed_events` | 用户需手动确认 | 有意为之，事实层不自动污染 |

## 10. 实现记录（M7）

实现与规格的偏差，逐条记理由：

| 偏差 | 规格原文 | 实现 | 理由 |
|---|---|---|---|
| 表里多了两个冗余列 | `shedding_states` 只列了 `image_id` 主键与识别结果字段 | 另加 `device_id` 与 `local_date` | 与 `frame_metrics` 同一做法：按设备与日期区间聚合时不必回连 `images` 大表，且 `local_date` 是按时区派生的，回连会引入时区依赖 |
| 降级时保留概率分布 | 「置信度低于阈值判 `unknown`」 | `unknown` 的 `confidence` 为 `null`，但 `probabilities` 完整写入 | 排查「模型到底看到了什么」需要原始分布；丢掉就只剩一个 `unknown` |
| 缺图日不打断事件推导 | 未说明 | `derive_events` 跳过 `state is None` 的日子 | 一天没拍到图不代表蜕皮结束了，打断序列会凭空造出 `shed_completed` |
| `labels.json` 多了 `input_size` | 只要求记录类别顺序 | 同时记录 `input_size`（默认 224） | 换骨干网络或改输入尺寸时，服务端不必改配置 |
| 新增 `api/params.py` | 未提及 | 把 `series.py` 里的 `_parse_day` 抽成共享的 `parse_day` | 两个序列端点都要解析日期，重复实现会漂移；顺带修掉 `date.fromisoformat` 接受 `2026-1-1` 的宽松行为 |
| ONNX 导出后要内联外部权重 | 未提及 | `ml/train_state_classifier.py` 的 `inline_external_data` | torch 导出器会把权重写成同名的 `.onnx.data`，服务端就得管两个文件；重新保存一次变成自包含的单文件 |

验收对照（10 条全部满足）：单图返回 200 与合法状态、未检出返回 `unknown`、低置信度降级但保留分布、幂等、模型未配置 503 且 `/readyz` 未就绪、众数聚合与平票优先级、无图日 `null`、事件推导、区间校验、类别顺序从 `labels.json` 读取。

二态占位模型的实测结果（`ml/runs/gecko-state/summary.json`）：

| 指标 | 数值 |
|---|---|
| 验证集最好准确率 | 0.9255 |
| 测试集准确率 | 0.9107 |
| `normal` | precision 0.9167 / recall 0.9625（80 张） |
| `shedding` | precision 0.8929 / recall 0.7812（32 张） |

比探路的 93.75% 低 2.7 点，原因是两者训练配置不同（探路用简单增强与 15 epoch 定学习率，这里加了 `RandomResizedCrop`、颜色抖动与余弦退火）。没有针对这批数据继续调参——它本来就不是产品数据，调出来的数字没有意义。

真机冒烟（`.tmp/smoke7.py`，端口 8128，真模型 + 真图）：`/readyz` 200；5 张蜕皮图里 4 张判 `shedding`（置信度 0.9969–1.0），1 张置信度 0.513 降级 `unknown` 且分布保留；3 张正常图全部判 `normal`（0.987–0.991）；逐日序列的投票、聚合、`current_state` 正确；倒序区间返回 `400 INVALID_REQUEST`。

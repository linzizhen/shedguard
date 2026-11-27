# 输入质量门（C 包「别瞎说话」）设计

> 状态：待批准
> 创建：2026-11-25
> 关联：`docs/plan.md` §4 主线第 1 项；前置 P22 `docs/robustness-2026-11-13.md`、P34 视觉重做。

## 1. 背景

现在的判定链路是：检测守宫 → 裁剪 → 分类器给三态概率 → 置信度低于 `state_min_confidence`（0.6）就记 `unknown`。

P22 的鲁棒性实测暴露了这套逻辑的根本缺陷：**模糊越重，模型越自信**。blur-7 下 valid 集蜕皮召回从 0.9231 掉到 0.3626，而平均置信度反而从 0.9557 升到 0.9770、unknown 率从 0.0172 降到 0.0086。也就是说，画面糊到看不清时，模型不但不弃权，还会用一个很高的置信度给出错误结论——「置信度阈值」这道安全网在最需要它的时候恰好失效。

对一个「拍照告诉用户守宫要不要蜕皮」的产品来说，这比直接说「看不清」糟糕得多：用户会照着错误的结论去调湿度、去等蜕皮。

## 2. 目标与非目标

**目标**：在分类之前先判断「这张图够不够看清」，不够就明确回一句「看不清，请重拍」，并告诉用户具体是哪里不行（太糊 / 太暗 / 太亮 / 没拍到），不再让模型对看不清的图发表意见。

**非目标（本设计不做）**：

- 不改分类模型、不重新训练、不调 `state_min_confidence` 的语义（阈值语义仍待真机数据，见 `docs/plan.md` §7）；
- 不做「拍歪了 / 角度不对」的几何判断（需要真机数据才知道什么叫歪）；
- 不做蒙白期识别（P13，需要数据）；
- 不做多帧融合或时序补判；
- 不改设备/摄像头自动抓拍链路的判定结果（见 4.5，同一套质量评估会被算出来并落库，但自动链路仍按 `unknown` 处理，不额外弹提醒）。

## 3. 范围

| 编号 | 事项 | 说明 |
| --- | --- | --- |
| C1 | 质量评估纯函数 | `domain/quality.py`：从一帧 + 检测框算出四项指标与判定结果 |
| C2 | 判定链路接入 | `SheddingService.analyze` 在分类之前评估；不通过直接记 `unknown` + 原因 |
| C3 | 落库 | `shedding_states` 新增 `quality_reason` 列（迁移 0011），`STATE_VERSION` 1 → 2 |
| C4 | 接口暴露 | `check-photo` 响应新增 `quality_reason`；`advice` 按原因给具体建议 |
| C5 | App 文案 | `resultCopy.ts` 按原因给「太糊 / 太暗 / 太亮 / 没拍到」四套人话 |
| C6 | 标定与验收脚本 | `ml/eval_quality_gate.py`：在 P22 退化集上复现覆盖率/拦截率数字 |
| C7 | 配置 | 四项阈值 + 一个总开关，全部可配 |

## 4. 设计

### 4.1 四项指标与阈值

指标都在**检测框外扩 8%（`state_crop_padding`）后的裁剪图**上算，并先缩放到 **224×224**——与分类器看到的输入完全一致，这样数值不随原图分辨率漂移。

| 指标 | 算法 | 阈值 | 判为 | 依据（见 §5） |
| --- | --- | --- | --- | --- |
| `sharpness` | 灰度拉普拉斯方差 | `< 25.0` | `too_blurry` | 干净图只误杀 1.2%，blur-7 拦下 62%、blur-5 拦下 25% |
| `lightness` | CIE L\* 均值 | `< 18.0` | `too_dark` | 干净图误杀 0.9%，bright-0.6 拦下 8% |
| `saturated` | 任一通道 ≥ 250 的像素占比 | `> 0.20` | `overexposed` | 干净图误杀 1.7%，bright-1.2 拦下 17% |
| 检测结果 | `detector.detect() is None` | — | `no_subject` | 复用现有「没找到守宫」判断 |

**被砍掉的候选：主体占比（检测框面积 / 整帧面积）**。原以为它能判「离太远」，实测发现**检测器会把守宫框撑满画面**：baseline 的 p05 是 0.549、p50 是 0.823，几乎没有低值。这个量衡量的是检测器有多贪心，不是用户拍得多远，做门只会白杀图。真正「没拍到」由 `detection is None` 覆盖。

**为什么过曝用「通道饱和」而不是「L\* ≥ 80 占比」**：L\* ≥ 80 在干净图上 p50 就有 0.037、p90 到 0.26、最大 0.619——浅色品系的守宫本身就大片高亮，用它会大量误杀。通道 ≥ 250 才是真正的削顶（数据丢失），干净图 p95 仅 0.053。

### 4.2 判定顺序

质量评估在**检测之后、分类之前**，因为需要检测框：

```
decode → detect
  ├─ None ──────────────────────────────→ unknown + no_subject（现状已如此）
  └─ 有框 → 裁剪 → 缩放到 224 → 算质量
        ├─ 不通过 ────────────────────→ unknown + 对应 reason（不进分类器）
        └─ 通过 → 分类 → 置信度门 → normal/opaque/shedding
```

**为什么不通过就不进分类器**：省一次推理；更重要的是语义上干净——「这张图不值得看」，与「看了但拿不准」是两件事，不该共用同一条置信度路径。

### 4.3 数据模型

`SheddingState` 新增 `quality_reason: str | None`（`None` 表示通过或未评估）。迁移 `0011_shedding_quality.py` 给 `shedding_states` 加一列 `quality_reason VARCHAR(16) NULL`。

`STATE_VERSION` 从 `"1"` 改为 `"2"`：判定规则变了，旧缓存必须重算，否则历史图会一直带着旧结论。重算发生在下次访问该图时（`analyze` 的缓存命中条件已包含 `state_version`）。

### 4.4 接口与文案

`PetCheckResult` 新增 `quality_reason: str | None`；`POST /api/v1/pets/{id}/check-photo` 响应体新增 `"quality_reason": "too_blurry" | "too_dark" | "overexposed" | "no_subject" | null`。

`advice` 优先按原因给（新增 `ADVICE_BY_QUALITY`），无原因时沿用现有 `ADVICE_BY_STATE`：

| reason | 建议文案 |
| --- | --- |
| `too_blurry` | 画面太糊了，手机拿稳一点、等它对上焦再拍一张。 |
| `too_dark` | 光线太暗，看不清皮肤。开个灯或者拿到亮一点的地方再拍。 |
| `overexposed` | 画面太亮，皮肤细节被光吃掉了。避开直射灯或反光再拍一张。 |
| `no_subject` | 画面里没找到守宫。把它放进取景框，拍全身再试一次。 |

App 侧 `app/src/lib/types.ts` 的 `CheckPhotoResult` 加 `quality_reason`；`app/src/lib/resultCopy.ts` 新增独立的 `QUALITY_COPY`（四条都是 `tone: 'unclear'`，`headline` 分别为「这张有点糊」「光线太暗了」「太亮了，看不清」「没找到守宫」），并新增 `resultCopy(state, qualityReason?)` 入口：**`qualityReason` 非空时优先用它，否则按 `state` 取原有文案**（实现上没往 `COPY` 里塞变体，避免 `Record<ShedState, …>` 的键类型被撑破）。首页徽标文案同步改为中性的「先重拍」，不再用「没看清」——否则「没找到守宫」的卡片上会顶着「没看清」，自相矛盾。

### 4.5 对自动抓拍链路的影响

设备与摄像头定时抓拍也走 `SheddingService.analyze`，所以质量评估同样生效：糊掉的帧会记 `unknown` 而不是猜一个状态。这是**期望行为**——`unknown` 不投票、不触发蜕皮提醒，比让一张糊图决定今天的状态安全。

但不额外产生「你的摄像头糊了」这类新提醒：P17 已有 `device_silent` / `no_detection` 兜底，再加一类会重复打扰。

### 4.6 配置

新增 5 项（59 → 64）：

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `quality_gate_enabled` | `false` | 总开关 |
| `quality_min_sharpness` | `25.0` | 低于则判太糊 |
| `quality_min_lightness` | `18.0` | 低于则判太暗 |
| `quality_max_saturated` | `0.20` | 高于则判过曝 |
| `quality_measure_size` | `224` | 指标计算分辨率，必须与分类器输入一致 |

**为什么默认关**：现有 536 个测试里有 10 多个文件用 `np.full((96,96,3), 180)` 这类**纯色块**当上传图，纯色块的拉普拉斯方差恒为 **0.00**（已实测），任何清晰度门都会把它们全部拒掉，那些测的是编排而不是像素的用例会集体失真。要一次性重写这十几个 fixture 不划算，也会让测试变得更脆。

所以沿用 P23/P24 的做法：**代码里默认关，在 `server/.env.example` 与演示启动脚本里显式打开**。测试通过 `Settings(_env_file=None, ...)` 构造，天然拿不到 `.env`，因此不受影响；专门的质量门测试自己传 `quality_gate_enabled=True` 并用有纹理的图。

**这意味着生产环境必须显式打开**——`.env.example`、`server/README.md`、`docs/public-demo.md` 三处都要写明。

## 5. 标定数据（本次实测）

方法：`ml/datasets/gecko-state-v2/valid` 全部 349 张 × 9 档条件（baseline、blur-3/5/7、bright-0.6/1.2、glare-strong、combo、frame-640）= 3141 次「退化 → 检测 → 裁剪 → 缩放 224 → 算指标 → 分类」，一次跑完落盘 `.tmp/quality_rows.jsonl`（分析脚本为一次性探针，不入库）。

**关键数字**：

| 条件 | 漏检 | sharpness p50 | 模型准确率（无门） | 蜕皮召回（无门） |
| --- | --- | --- | --- | --- |
| baseline | 8/349 | 518.6 | 0.934 | 0.923 |
| blur-3 | 30/349 | 98.0 | 0.819 | 0.615 |
| blur-5 | 47/349 | 46.9 | 0.734 | 0.451 |
| blur-7 | 81/349 | 19.3 | 0.625 | 0.319 |
| combo | 48/349 | 71.5 | 0.765 | 0.571 |
| bright-1.2 | 7/349 | 705.9 | 0.928 | 0.923 |

**阈值扫描（清晰度单门，在「干净且判对」的 326 张上）**：

| 阈值 | 干净图误杀 | blur-7 拦下 | blur-5 拦下 |
| --- | --- | --- | --- |
| 15 | 0.3% | 34% | 11% |
| 20 | 0.6% | 53% | 18% |
| **25** | **1.2%** | **62%** | **25%** |
| 30 | 1.8% | 68% | 32% |
| 40 | 2.5% | 77% | 44% |

**必须诚实写下来的一条**：门**不会提高模型的准确率**。按档统计「被门拒掉的图」与「通过门的图」的模型错误率，多数档位上被拒的那组错误率反而更低（blur-3：被拒 4.3% vs 通过 10.8%）。原因是糊图会让模型塌缩到预测 `normal`，而 `normal` 占数据 74%，糊掉的图里恰好多数真的是 `normal`。

所以质量门的作用不是「筛出更准的子集」，而是**在模型无法可靠判断时拒绝发言**。验收标准据此写成行为断言（糊图大多回「看不清」），不写成准确率提升。

### 5.1 补测：门放行之后还剩多少「确定的错」

实现完成后又回头算了一遍「被门放行、但模型把蜕皮判成别的」有多少张（349 张 × 9 档逐行数据）：

| 条件 | 总数 | 放行 | 放行但判错 | 其中把蜕皮判成别的 |
|---|---|---|---|---|
| baseline | 349 | 327 | 14 | 6 |
| blur-3 | 349 | 280 | 30 | 29 |
| blur-5 | 349 | 224 | 38 | 37 |
| blur-7 | 349 | **99** | 21 | **20** |
| bright-0.6 | 349 | 293 | 15 | 9 |
| bright-1.2 | 349 | 273 | 11 | 5 |
| glare-strong | 349 | 324 | 16 | 8 |
| combo | 349 | 261 | 30 | 27 |
| frame-640 | 349 | 327 | 14 | 7 |

重模糊从 349 张压到 99 张（−72%），但**剩下这 99 张里仍有 20 张把蜕皮判成别的**——那些图还留着一点纹理，清晰度刚好卡在 25 之上。这不是实现 bug，是阈值本身的取舍：把 T 提到 40 能把 blur-7 的漏判从 20 降到 14，代价是干净图多拒 4 张；提到 65 能降到 9，但干净图要拒 38 张。**默认取 25 是「宁可少拒好图」的选择**，真机数据到手后应重标（`docs/plan.md` §7）。

## 6. 实施顺序

1. C1 `domain/quality.py` + 单元测试（纯色块 → 太糊；棋盘格 → 通过；暗图 → 太暗；白斑 → 过曝）；
2. C3 迁移 0011 + `SheddingState` 字段 + `STATE_VERSION` 2；
3. C2 `SheddingService` 接入 + 集成测试（门开 / 门关两条路径）；
4. C4 `PetCheckResult` 与 `check-photo` 响应 + 测试；
5. C5 App 类型与文案；
6. C6 `ml/eval_quality_gate.py` 复现 §5 的数字；
7. C7 配置项 + `.env.example` + `server/.env`（本地打开）；
8. 文档：`docs/plan.md` 登记 P35、`docs/handoff.md` 同步、`server/README.md` 说明开关；
9. 质量门：`pytest`（536 + 新增，覆盖率 ≥ 85%）、`ruff check .`、`mypy src tests`、App `tsc --noEmit` / `eslint`。

## 7. 验收标准

1. **纯色块被拒**：用 `np.full((96,96,3), 180)` 调 `check-photo`（门打开）→ `state == "unknown"`、`quality_reason == "too_blurry"`、`advice` 含「糊」。
2. **有纹理的图通过**：棋盘格图 → `quality_reason is None`，`state` 由分类器决定。
3. **门关时行为不变**：`quality_gate_enabled=False` 时纯色块仍按分类器结果返回，`quality_reason` 为 `None`。
4. **暗图 / 过曝图**：构造 L\* 均值 < 18 的图 → `too_dark`；构造大片 255 白斑的图 → `overexposed`。
5. **没拍到**：`detection is None` → `no_subject`（现有 `unknown` 路径带上原因）。
6. **自动链路不受污染**：糊图入库后记 `unknown`，不产生 `shedding_detected` 提醒。
7. **标定脚本可复现**：`ml/eval_quality_gate.py` 输出的 baseline 误杀率与 blur-7 拦截率与 §5 一致（±0.02）。
8. **既有质量门全绿**：536 个测试一个不坏；`ruff` / `mypy` / `tsc` / `eslint` 全绿。

## 8. 风险

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 阈值是网图标定的，不是真实饲养箱 | 数据全部来自公开图片，640×480 隔玻璃反光的真实场景没覆盖 | 阈值全部可配；`docs/plan.md` §7 记一条「待真机标定」；P31 收到真实图后重跑 §5 |
| 默认关 → 生产忘了开 | 开关在代码里默认 `false` | `.env.example`、`server/.env`、`server/README.md`、`docs/public-demo.md` 四处写明；`/healthz` 之外再加一条启动日志「质量门已启用/未启用」 |
| 误杀好图 | 干净图 1.2% 被判太糊（多为极浅色或极平整背景） | 阈值可调；被拒文案引导重拍，代价是用户多点一次，不是错误结论 |
| `STATE_VERSION` 升级触发重算 | 历史图下次访问时重算，糊图会从某个确定状态变成 `unknown` | 这是修正而非退化；`docs/handoff.md` 里注明 |
| 门不提高准确率，可能被认为「没用」 | §5 已实测说明 | 验收写成行为断言；文档里明确它的定位是「拒绝发言」而不是「筛更准的子集」 |

## 9. 影响面

- 服务端新增：`domain/quality.py`、`migrations/versions/0011_shedding_quality.py`、`tests/unit/test_quality_domain.py`、`tests/integration/test_quality_gate.py`。
- 服务端修改：`domain/models.py`（+1 字段）、`domain/pets.py`（+1 字段）、`infra/tables.py`（+1 列）、`services/shedding.py`（接入 + `STATE_VERSION`）、`services/pets.py`（建议文案）、`api/routes/pets.py`（响应体）、`config.py`（+5 项）、`migrations/env.py` 无需改。
- App：`lib/types.ts`、`lib/resultCopy.ts`、`app/(tabs)/index.tsx`（结果卡透传 reason）。
- 新增脚本：`ml/eval_quality_gate.py`。
- 文档：`docs/plan.md`、`docs/handoff.md`、`server/README.md`、`docs/public-demo.md`、`server/.env.example`。

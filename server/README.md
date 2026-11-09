# shedguard-server

爬宠蜕皮预警系统的后端服务。负责接收设备上传的照片、按日期与设备归档、把元数据写入 SQLite，并把每天的照片收敛成可供每日对比分析消费的序列，同时记录人工标注的蜕皮事件、计算体表指标、判定蜕皮状态。App 上线后新增宠物档案、手动蜕皮日志、下一次蜕皮预测、拍照查验、护理知识库与卡皮风险评估六组接口。

设计依据：

- [`../docs/specs/2026-11-02-server-image-ingest-design.md`](../docs/specs/2026-11-02-server-image-ingest-design.md)（M1/M2 图片接入）
- [`../docs/specs/2026-11-02-series-and-events-design.md`](../docs/specs/2026-11-02-series-and-events-design.md)（M3 时序输入层）
- [`../docs/specs/2026-11-02-shed-detection-core-design.md`](../docs/specs/2026-11-02-shed-detection-core-design.md)（M5 信号层）
- [`../docs/specs/2026-11-02-shed-judgement-design.md`](../docs/specs/2026-11-02-shed-judgement-design.md)（M6 判定层）
- [`../docs/specs/2026-11-04-shedding-state-design.md`](../docs/specs/2026-11-04-shedding-state-design.md)（蜕皮状态识别）
- [`../docs/specs/2026-11-09-app-and-firmware-design.md`](../docs/specs/2026-11-09-app-and-firmware-design.md)（App 与固件配套接口）

## 当前进度

- M1（工程骨架）：配置校验、结构化日志、统一错误契约、健康检查——已完成。
- M2（图片接入）：上传、幂等去重、按天列表、取原图与元数据、Alembic 迁移——已完成。
- M3（时序输入层）：每日代表帧选择、区间序列查询、蜕皮事件记录——已完成。
- M5（信号层）：检测器抽象、六项体表指标、光照归一化、指标落库与查询——已完成。
- M4（定位模型）：YOLOv8n 训练完成，测试集 mAP50 0.902，ONNX 已接入。
- M6（判定层）：稳健 Z 分数、方向性判定、告警状态与趋势端点——已完成。
- M7（蜕皮状态识别）：定位 + 独立分类器、四态判定、每日投票聚合、事件由状态转换推导——已完成，分类模型为二态占位。
- M8（App 配套接口）：宠物档案、手动蜕皮日志、下一次蜕皮预测、拍照查验聚合、护理知识库、卡皮风险评估——已完成。

## 运行

```powershell
# 在仓库根目录
.\.venv\Scripts\python.exe -m pip install -r server\requirements.lock

# 启动服务（默认 127.0.0.1:8000）
$env:PYTHONPATH = "server\src"
.\.venv\Scripts\python.exe -m shedguard_server
```

服务启动时自动执行 `alembic upgrade head`，无需手工建表。检查存活与就绪：

```powershell
curl.exe http://127.0.0.1:8000/healthz
curl.exe http://127.0.0.1:8000/readyz
```

## 接口

所有响应都带 `X-Request-Id`；错误响应体统一为：

```json
{"error": {"code": "NOT_FOUND", "message": "资源不存在", "request_id": "01JC..."}}
```

### 上传图片

`POST /api/v1/images`，支持两种请求体：

1. `multipart/form-data`，文件字段名 `file`；
2. 裸请求体，`Content-Type` 为 `image/*`。

可选请求头：

| 头 | 说明 |
|---|---|
| `X-Device-Id` | 设备标识，`^[A-Za-z0-9_-]{1,64}$`，缺省 `unknown` |
| `X-Captured-At` | 拍摄时间，RFC 3339；缺省取服务端接收时间 |

- 新建返回 `201`，同一张图（按 SHA-256 判定）重复上传返回 `200` 且 `duplicate: true`。
- 扩展名由文件魔数决定（JPEG / PNG），不信任 `Content-Type`。

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/images -H "X-Device-Id: cam-1" -F "file=@shed.jpg"
```

### 按天查询

`GET /api/v1/images?date=YYYY-MM-DD&device_id=cam-1&limit=100&offset=0`

`date` 缺省为服务端当天，`limit` 取值 1–500。响应为 `{items, total, limit, offset}`。

### 取原图与元数据

- `GET /api/v1/images/{id}`：返回原图字节，带 `ETag`（SHA-256）与 `Cache-Control: immutable`。
- `GET /api/v1/images/{id}/metadata`：返回该图的元数据 JSON。

### 每日序列

`GET /api/v1/series?device_id=cam-1&from=2026-11-01&to=2026-11-14`

把区间内每一天收敛成一条代表帧，无图日也返回（`image_id` 为 `null`）：

```json
{
  "device_id": "cam-1",
  "from": "2026-11-01",
  "to": "2026-11-03",
  "days": [
    {"date": "2026-11-01", "image_id": "01J...", "captured_at_utc": "2026-11-01T12:03:00Z", "in_window": true, "total_images": 3},
    {"date": "2026-11-02", "image_id": null, "captured_at_utc": null, "in_window": false, "total_images": 0}
  ],
  "total_days": 3,
  "missing_days": 1
}
```

代表帧规则：取离当天目标时刻（`SHEDGUARD_CAPTURE_HOUR`，默认 20:00，按 `SHEDGUARD_TIMEZONE` 解释）最近的一张，窗口为 ±`SHEDGUARD_CAPTURE_WINDOW_MINUTES`（默认 180 分钟）。

- 窗口内有图：`in_window: true`。
- 窗口内无图：仍返回当天最近的一张，但标 `in_window: false`，由消费方决定是否降级使用。
- 区间天数上限 366。

### 蜕皮事件

- `PUT /api/v1/shed-events/{device_id}/{event_date}`：写入或覆盖，请求体 `{"outcome": "...", "notes": "..."}`。新建 `201`，覆盖 `200` 且 `id` 不变。
- `GET /api/v1/shed-events?device_id=cam-1&from=2026-10-01&to=2026-11-30`：按设备与区间查询，按日期降序。

`outcome` 四选一：`completed`（蜕完）、`partial`（有残留）、`stuck`（卡皮）、`unknown`（事后补录）。`notes` 上限 2000 字符。

```powershell
curl.exe -X PUT http://127.0.0.1:8000/api/v1/shed-events/cam-1/2026-11-05 -H "Content-Type: application/json" -d '{\"outcome\":\"completed\",\"notes\":\"整体顺利\"}'
```

## 图像分析

### 计算单帧指标

`POST /api/v1/analysis/{image_id}`，同步返回该帧的体表指标。同一张图、同一检测器、同一指标版本重复调用直接返回已有记录（幂等）。

```json
{
  "image_id": "0f1e...",
  "device_id": "cam-1",
  "local_date": "2026-11-02",
  "detected": true,
  "box": [120, 88, 501, 402],
  "detector_name": "onnx:gecko-det",
  "detector_confidence": 0.91,
  "normalized": true,
  "exposure_scale": 0.93,
  "lightness_mean": 62.4,
  "lightness_std": 14.1,
  "saturation_mean": 0.28,
  "high_light_ratio": 0.07,
  "edge_density": 0.11,
  "color_entropy": 2.94,
  "background_lightness": 58.2,
  "computed_at_utc": "2026-11-02T12:30:00Z",
  "metrics_version": "1"
}
```

- 检测不到守宫时 `detected: false`，六项指标与 `box` 均为 `null`。
- `lightness_*` 是 CIE L\*（0–100），不是 0–255 亮度。
- `exposure_scale` 是「当天背景亮度 ÷ 近 7 天背景亮度中位数」，用来抵消灯光与曝光漂移；`normalized: true` 表示做了校正。

`SHEDGUARD_DETECTOR_MODEL` 为空时使用空检测器，整张图当作身体，只适合验证链路、不适合真实判断。

## 判定信号

### 查询逐日判定

`GET /api/v1/series/{device_id}/signals?from=2026-11-01&to=2026-11-14`

返回区间内每一天的判定状态。基线会越过区间左端向前回看 `SHEDGUARD_BASELINE_DAYS` 天，因此查询「最近七天」也能拿到足够样本：

```json
{
  "device_id": "cam-1",
  "from": "2026-11-01",
  "to": "2026-11-03",
  "days": [
    {
      "date": "2026-11-01",
      "image_id": "0f1e...",
      "metrics": {"lightness_mean": 62.4, "...": 0.0},
      "z_scores": {"lightness_mean": 0.41, "...": 0.0},
      "hits": [],
      "state": "normal",
      "baseline_samples": 12
    }
  ],
  "alert_days": 0,
  "current_state": "normal"
}
```

四种状态：

| 状态 | 含义 |
|---|---|
| `insufficient` | 基线样本不足 `SHEDGUARD_MIN_BASELINE_SAMPLES`，还判断不了 |
| `normal` | 没有命中 |
| `watch` | 命中数达标，但还没连续够天数 |
| `alert` | 连续 `SHEDGUARD_ALERT_CONSECUTIVE_DAYS` 天，每天命中 ≥ `SHEDGUARD_ALERT_MIN_SIGNALS` 个指标 |

判定细节：

- 偏离度用中位数 + MAD 的稳健 Z 分数，不用标准差——蜕皮当天本身就是离群点，会把标准差撑大。
- 只认符合蜕皮方向的越界：亮度升高、饱和度降低、高光增多、纹理变密。亮度大幅**下降**不算命中。
- 无图日与未检出守宫的日子会清空连续计数，不会跨过缺口累积。
- 区间天数上限 366，`from` 不得晚于 `to`。

## 蜕皮状态识别

判定层回答「指标有没有异常偏移」，状态识别回答「守宫现在处于蜕皮的哪个阶段」。两者独立：前者是纯统计，后者是一个独立训练的视觉分类器。

### 识别单张图片

`POST /api/v1/shedding/{image_id}`：取图 → 定位守宫 → 按框裁剪（外扩 `SHEDGUARD_STATE_CROP_PADDING`）→ 缩放到 224×224 → 分类 → 落库。

```json
{
  "image_id": "0f1e...",
  "device_id": "cam-1",
  "date": "2026-11-04",
  "state": "shedding",
  "confidence": 0.9969,
  "probabilities": {"normal": 0.0031, "shedding": 0.9969},
  "detector_name": "onnx:gecko-det",
  "classifier_name": "onnx:gecko-state",
  "state_version": "1",
  "box": [120, 88, 402, 310],
  "computed_at_utc": "2026-11-04T02:15:11Z"
}
```

四种状态：

| 状态 | 含义 | 谁判定 |
|---|---|---|
| `normal` | 体色正常，没有蜕皮迹象 | 分类器 |
| `opaque` | 蒙白：体色发白、图案对比度下降，皮还完整 | 分类器 |
| `shedding` | 蜕皮中：皮正在脱落 | 分类器 |
| `unknown` | 判断不了 | 服务层：未检出守宫，或最高置信度低于 `SHEDGUARD_STATE_MIN_CONFIDENCE` |

`unknown` 不是模型的输出类别。分类器永远只能输出具体状态，降级到 `unknown` 由服务层做——这样「模型没把握」和「模型认为正常」不会被混为一谈。降级时 `confidence` 为 `null`，但 `probabilities` 完整保留，便于排查模型到底看到了什么。

同一张图重复调用返回既有结果，幂等键是 `(state_version, classifier_name)`：换了模型会重新识别，不换就复用。

### 查询逐日状态

`GET /api/v1/series/{device_id}/shedding?from=2026-11-01&to=2026-11-14`

```json
{
  "device_id": "cam-1",
  "from": "2026-11-01",
  "to": "2026-11-03",
  "days": [
    {"date": "2026-11-01", "state": "normal", "votes": {"normal": 2, "opaque": 0, "shedding": 0}, "image_count": 2},
    {"date": "2026-11-02", "state": "opaque", "votes": {"normal": 0, "opaque": 3, "shedding": 1}, "image_count": 4},
    {"date": "2026-11-03", "state": "shedding", "votes": {"normal": 0, "opaque": 0, "shedding": 2}, "image_count": 2}
  ],
  "events": [
    {"type": "shed_started", "date": "2026-11-02", "previous": "normal", "current": "opaque"}
  ],
  "current_state": "shedding"
}
```

聚合与事件规则：

- 当天所有已识别图片投票，`unknown` 不参与；取众数，平票按 `shedding > opaque > normal` 排序——漏报一次蜕皮的代价高于让用户多看一眼。
- 当天没有可用图片时 `state` 为 `null`，不是 `normal`。「无法判断」和「一切正常」是两回事。
- 事件由状态转换推导，不单独存表：`normal` → `opaque`/`shedding` 记 `shed_started`；反向记 `shed_completed`；`opaque` ↔ `shedding` 不算事件（同一次蜕皮的内部阶段变化）。
- 「已蜕完」不是视觉状态，而是「蜕皮中 → 正常」这次转换。
- 缺图日不打断序列，只被跳过；但连续两天状态相同不会重复发事件。
- 区间天数上限 366，`from` 不得晚于 `to`。

### 类别顺序由模型决定

服务端不硬编码 `normal/opaque/shedding`，而是从 `SHEDGUARD_STATE_MODEL` 同名的 `.labels.json` 读取：

```json
{"labels": ["normal", "shedding"], "input_size": 224}
```

所以换模型只换文件：当前是二态（没有蒙白数据），等蒙白样本到位后重新训练三态模型、替换 `.onnx` 与 `.labels.json`，服务端代码一行不改。

### 已知限制

当前分类模型是在公开爬宠数据集上训的二态占位模型（`ml/README.md` 有训练细节）：训练集物种混杂、没有红外图、**蒙白类样本为零**。它能证明链路通，不能当作产品精度。详见规格第 9 节。

## 宠物档案与蜕皮日志（App 接口）

面向手机 App 的六组接口，设计依据见规格 `2026-11-09-app-and-firmware-design.md`。

### 宠物档案

- `GET /api/v1/pets`：列表，按创建时间倒序。
- `POST /api/v1/pets`：新建，请求体 `{"name": "小橘", "species": "豹纹守宫", "morph": "橘化", "birth_date": "2025-06-01"}`，只有 `name` 必填（非空、≤64 字符），上限 20 只。
- `GET /api/v1/pets/{pet_id}`、`PUT /api/v1/pets/{pet_id}`、`DELETE /api/v1/pets/{pet_id}`（级联删除蜕皮记录）。

### 蜕皮日志

- `GET /api/v1/pets/{pet_id}/shed-records`：按开始日倒序。
- `POST /api/v1/pets/{pet_id}/shed-records`：`{"started_on": "2026-10-25", "completed_on": "2026-10-27", "notes": "完整蜕皮"}`。`completed_on` 可空（进行中），早于 `started_on` 报 400，同宠物同开始日报 `409 CONFLICT`。
- `PUT /api/v1/pets/{pet_id}/shed-records/{record_id}`、`DELETE .../{record_id}`。

### 下一次蜕皮预测

`GET /api/v1/pets/{pet_id}/shed-prediction?today=YYYY-MM-DD`（`today` 缺省取服务端当天）：

```json
{
  "pet_id": "01M6...",
  "predictable": true,
  "reason": null,
  "median_interval_days": 27,
  "mad_days": 3,
  "next_window_start": "2026-11-18",
  "next_window_end": "2026-11-24",
  "based_on_cycles": 2,
  "today": "2026-11-09"
}
```

- 至少 3 条**完整**记录（有 `completed_on`）才能算出 ≥2 个间隔；不足时 `predictable: false` 并说明原因。
- 预测窗口 = 最后一次开始日 + (中位间隔 − MAD) 到 (中位间隔 + MAD)；窗口已过则判不可预测并提示确认是否有漏记。

### 拍照查验（聚合端点）

`POST /api/v1/pets/{pet_id}/check-photo`，`multipart/form-data`（字段 `file`）或裸 `image/*` 请求体。一次调用完成：上传（`device_id` 为 `pet-{pet_id}`）→ 定位 → 分类 → 返回状态与照护建议：

```json
{
  "image_id": "01M6...",
  "state": "shedding",
  "confidence": 0.9985,
  "probabilities": {"normal": 0.0015, "shedding": 0.9985},
  "advice": "守宫正在蜕皮。保持饲养箱湿度在 50% 以上，提供湿润躲避穴，切勿强行撕扯皮肤；..."
}
```

`advice` 按四态映射：正常给观察要点、蒙白给加湿建议、蜕皮中给环境管理提醒、未知建议重拍。状态分类模型未配置时返回 `503 MODEL_UNAVAILABLE`。

### 护理知识库

- `GET /api/v1/knowledge/topics`：话题列表（overview / environment / feeding / shedding-basics / stuck-shed / hydration），静态内容不走数据库。
- `GET /api/v1/knowledge/topics/{slug}`：话题详情，`sections` 为标题+要点数组。未知 slug 返回 404。

内容来源 `docs/gecko-params.md`（已核实修订，来源分级见该文档）。

### 卡皮风险评估

`POST /api/v1/risk-assessment`，请求体六道单选题：

```json
{
  "last_shed_complete": "complete | partial | stuck | unknown",
  "eye_condition": "clear | dull | retained_spectacle",
  "toe_condition": "normal | discolored | swollen",
  "hydration": "daily | occasional | rarely_never",
  "humidity": "below_30 | unknown | above_50",
  "water_bowl": "fresh_daily | stale_or_absent"
}
```

规则引擎打分（部分残留/大片残留 +3、眼部残留 +3 且附带就医警告、脚趾肿胀 +3 / 变色 +2、饮水极少 +2、湿度不足或未知 +1、水碗不洁 +1），0–1 `low`、2–4 `moderate`、≥5 `high`；响应含逐项 `factors` 说明与 `vet_warning`（仅眼部残留触发）。

### App 接口错误码补充

| 码 | 状态 | 触发场景 |
|---|---|---|
| `CONFLICT` | 409 | 同宠物同日已有蜕皮记录 |


### 错误码

| 码 | 状态 | 触发场景 |
|---|---|---|
| `INVALID_REQUEST` | 400 | 参数或请求头非法 |
| `EMPTY_PAYLOAD` | 400 | 请求体为空 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 魔数既非 JPEG 也非 PNG |
| `PAYLOAD_TOO_LARGE` | 413 | 超过 `SHEDGUARD_MAX_UPLOAD_BYTES` |
| `NOT_FOUND` | 404 | 图片或宠物不存在 |
| `CONFLICT` | 409 | 同宠物同开始日已有蜕皮记录 |
| `STORAGE_UNAVAILABLE` | 503 | 数据目录、数据库或模型文件不可用 |
| `MODEL_UNAVAILABLE` | 503 | 状态分类模型未配置或加载失败 |
| `INTERNAL_ERROR` | 500 | 未预期异常 |

## 配置

全部通过环境变量或 `server/.env` 提供，启动时校验，非法值直接失败。

| 变量 | 缺省值 | 说明 |
|---|---|---|
| `SHEDGUARD_DATA_DIR` | `./data` | 图片与数据库所在目录 |
| `SHEDGUARD_DB_URL` | 由 `data_dir` 派生 | 显式指定时覆盖派生值 |
| `SHEDGUARD_HOST` | `127.0.0.1` | 监听地址 |
| `SHEDGUARD_PORT` | `8000` | 监听端口 |
| `SHEDGUARD_MAX_UPLOAD_BYTES` | `10485760` | 单张图片上限 |
| `SHEDGUARD_TIMEZONE` | `Asia/Shanghai` | 计算 `local_date` 与代表帧目标时刻用 |
| `SHEDGUARD_CAPTURE_HOUR` | `20` | 每日代表帧的目标整点（0–23） |
| `SHEDGUARD_CAPTURE_WINDOW_MINUTES` | `180` | 目标时刻两侧的容差窗口（0–720） |
| `SHEDGUARD_DETECTOR_MODEL` | 空 | ONNX 检测模型路径；为空则用空检测器 |
| `SHEDGUARD_DETECT_MIN_CONFIDENCE` | `0.35` | 检测框置信度下限（0–1） |
| `SHEDGUARD_BACKGROUND_DAYS` | `7` | 计算曝光参考值回看的有效天数（1–60） |
| `SHEDGUARD_BASELINE_DAYS` | `14` | 判定时回看的历史天数（3–90） |
| `SHEDGUARD_MIN_BASELINE_SAMPLES` | `7` | 判定所需的最少基线样本数（3–90） |
| `SHEDGUARD_ROBUST_Z_THRESHOLD` | `2.0` | 单指标越界的稳健 Z 阈值（1.0–6.0） |
| `SHEDGUARD_ALERT_MIN_SIGNALS` | `2` | 触发所需的最少命中指标数（1–6） |
| `SHEDGUARD_ALERT_CONSECUTIVE_DAYS` | `2` | 触发所需的连续天数（1–7） |
| `SHEDGUARD_STATE_MODEL` | 空 | ONNX 状态分类模型路径；为空则识别接口返回 503 |
| `SHEDGUARD_STATE_MIN_CONFIDENCE` | `0.6` | 低于此置信度降级为 `unknown`（0–1） |
| `SHEDGUARD_STATE_CROP_PADDING` | `0.08` | 按检测框裁剪时的外扩比例（0–0.3） |
| `SHEDGUARD_LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `SHEDGUARD_LOG_FORMAT` | `json` | `json` 或 `console` |

## 存储布局

```
<DATA_DIR>/
  shedguard.db
  images/YYYY-MM-DD/<device_id>/HHMMSS_<sha8>.<jpg|png>
```

文件先写同目录临时文件再原子重命名；路径完全由服务端生成，不接受客户端指定。

## 迁移

```powershell
cd server
..\.venv\Scripts\alembic.exe -c alembic.ini revision -m "说明"
..\.venv\Scripts\alembic.exe -c alembic.ini upgrade head
```

服务启动时也会自动升级到最新版本；迁移失败不会阻断进程启动，`/readyz` 会持续返回 503 提示。

## 开发

```powershell
cd server
..\.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing
..\.venv\Scripts\ruff.exe check .
..\.venv\Scripts\mypy.exe
```

覆盖率门槛见 `pyproject.toml`（总体 85%）；业务层 `domain`、`services` 实测 90% 以上。

## 目录结构

```
server/
  pyproject.toml        项目配置与工具链
  alembic.ini           迁移配置
  requirements.lock     运行期依赖锁定
  .env.example          配置样例
  src/shedguard_server/
    app.py              应用装配
    config.py           配置模型
    errors.py           错误契约
    logging_setup.py    结构化日志
    ids.py              请求 ID 生成
    api/
      dependencies.py   依赖装配
      params.py         查询参数解析
      routes/           HTTP 路由（health / images / series / shed-events / analysis / shedding / pets / knowledge / risk）
    domain/             领域规则（校验、命名、时间、序列、事件、成像、检测、指标、判定、蜕皮状态、宠物、知识、风险）
    services/           用例编排
    infra/              数据库、存储、迁移执行、图像解码、ONNX 检测器与分类器
    migrations/         Alembic 版本
  tests/
    unit/               领域与工具层
    integration/        HTTP 端到端
```

## 已知欠账

无鉴权、无 HTTPS、无留存策略、无磁盘配额、无限流、无备份、存储未加密。详见设计规格第 16 节。
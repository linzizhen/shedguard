# shedguard-server

爬宠蜕皮预警系统的后端图片接入服务。负责接收设备上传的照片、按日期与设备归档、把元数据写入 SQLite，并把每天的照片收敛成可供每日对比分析消费的序列，同时记录人工标注的蜕皮事件。

设计依据：

- [`../docs/specs/2026-11-02-server-image-ingest-design.md`](../docs/specs/2026-11-02-server-image-ingest-design.md)（M1/M2 图片接入）
- [`../docs/specs/2026-11-02-series-and-events-design.md`](../docs/specs/2026-11-02-series-and-events-design.md)（M3 时序输入层）
- [`../docs/specs/2026-11-02-shed-detection-core-design.md`](../docs/specs/2026-11-02-shed-detection-core-design.md)（M5 信号层）

## 当前进度

- M1（工程骨架）：配置校验、结构化日志、统一错误契约、健康检查——已完成。
- M2（图片接入）：上传、幂等去重、按天列表、取原图与元数据、Alembic 迁移——已完成。
- M3（时序输入层）：每日代表帧选择、区间序列查询、蜕皮事件记录——已完成。
- M5（信号层）：检测器抽象、六项体表指标、光照归一化、指标落库与查询——已完成。
- M4（定位模型训练）：数据集转换脚本已就绪，模型待训练。

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

### 错误码

| 码 | 状态 | 触发场景 |
|---|---|---|
| `INVALID_REQUEST` | 400 | 参数或请求头非法 |
| `EMPTY_PAYLOAD` | 400 | 请求体为空 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 魔数既非 JPEG 也非 PNG |
| `PAYLOAD_TOO_LARGE` | 413 | 超过 `SHEDGUARD_MAX_UPLOAD_BYTES` |
| `NOT_FOUND` | 404 | 图片不存在 |
| `STORAGE_UNAVAILABLE` | 503 | 数据目录或数据库不可用 |
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
      routes/           HTTP 路由（health / images / series / shed-events / analysis）
    domain/             领域规则（校验、命名、时间、序列、事件、成像、检测、指标）
    services/           用例编排
    infra/              数据库、存储、迁移执行、图像解码、ONNX 检测器
    migrations/         Alembic 版本
  tests/
    unit/               领域与工具层
    integration/        HTTP 端到端
```

## 已知欠账

无鉴权、无 HTTPS、无留存策略、无磁盘配额、无限流、无备份、存储未加密。详见设计规格第 16 节。
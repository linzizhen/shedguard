# shedguard-server

爬宠蜕皮预警系统的后端图片接入服务。负责接收设备上传的照片、按日期与设备归档、把元数据写入 SQLite，并为后续的每日对比分析提供查询接口。

设计依据见 [`../docs/specs/2026-11-02-server-image-ingest-design.md`](../docs/specs/2026-11-02-server-image-ingest-design.md)。

## 当前进度

- M1（工程骨架）：配置校验、结构化日志、统一错误契约、健康检查——已完成。
- M2（图片接入）：上传、幂等去重、按天列表、取原图与元数据、Alembic 迁移——已完成。

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
| `SHEDGUARD_TIMEZONE` | `Asia/Shanghai` | 计算 `local_date` 用 |
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
    api/routes/         HTTP 路由
    domain/             领域规则（校验、命名、时间）
    services/           用例编排
    infra/              数据库、存储、迁移执行
    migrations/         Alembic 版本
  tests/
    unit/               领域与工具层
    integration/        HTTP 端到端
```

## 已知欠账

无鉴权、无 HTTPS、无留存策略、无磁盘配额、无限流、无备份、存储未加密。详见设计规格第 16 节。
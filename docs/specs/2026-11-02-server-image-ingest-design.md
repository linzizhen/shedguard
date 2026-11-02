# 后端图片接入服务设计规格

> 状态：**待审阅**
> 日期：2026-11-02
> 范围：shedguard 后端第一个可运行子系统 —— 图片接收、落盘、元数据存储与查询
> 标准：商业级工程标准（架构分层、类型契约、可测试、可观测、可演进）
> 路径分类：架构级（`server/` 此前为空目录，属新建子系统）

---

## 1. 背景与目标

### 1.1 背景

固件侧 P0 目标是「ESP32-S3-EYE 定时拍照 → WiFi 上传」。上传必须有真实可投递的端点才能联调，因此后端需要先于固件存在。

同时，蜕皮识别的核心算法是「固定机位 + 每日对比 + 时序判断」，其数据基础是**按日归档的原始图片与可靠元数据**。这一层如果现在做错，后面的白度分析、时序对比都会建立在脏数据上。

### 1.2 目标

1. 提供稳定的图片接收接口，支持 ESP32 直发的 raw body 与 curl 使用的 multipart 两种形态
2. 图片按本地日期分目录归档，元数据入库，支持按日期与设备检索
3. 上传具备幂等性，断网补传不会产生重复记录
4. 代码质量达到商业级工程标准，可被后续模块（图像分析、判定、推送）安全复用

### 1.3 非目标（本轮明确不做）

- 图像分析（白度、浑浊度、活动量）
- 蜕皮判定与提醒推送
- 前端页面
- 鉴权、HTTPS、限流、备份
- 多设备管理与设备注册流程

---

## 2. 术语

| 术语 | 含义 |
|---|---|
| 抓拍（capture） | 设备一次快门产生的单张图片 |
| 本地日期（local date） | 按服务端配置时区换算出的日历日期，是每日对比的分片键 |
| 幂等命中 | 同一图片内容重复上传时，返回既有记录而非新建 |

---

## 3. 架构

### 3.1 分层

```
HTTP 层  ── 路由、请求解析、响应序列化、状态码
应用层  ── 用例编排：校验 → 落盘 → 入库 → 返回
领域层  ── 业务规则：内容校验、幂等判定、路径生成、时区换算
基础设施 ── SQLite 连接、文件系统、配置、日志
```

依赖方向单向向下：HTTP 层不得直接访问数据库或文件系统。

### 3.2 目录结构

```text
server/
├── pyproject.toml              # 依赖声明与工具配置
├── requirements.lock           # 锁定版本，用于可复现构建
├── .env.example                # 配置样例
├── README.md                   # 运行与联调说明
├── src/shedguard_server/
│   ├── __main__.py             # python -m shedguard_server 入口
│   ├── app.py                  # 应用工厂 create_app()
│   ├── config.py               # pydantic-settings 配置
│   ├── errors.py               # 错误码枚举与异常类型
│   ├── logging_setup.py        # JSON 日志与 request_id 上下文
│   ├── api/
│   │   ├── middleware.py       # request_id、访问日志、异常转换
│   │   └── routes/
│   │       ├── health.py       # /healthz /readyz
│   │       └── images.py       # /api/v1/images
│   ├── domain/
│   │   ├── models.py           # ImageRecord、UploadResult 等值对象
│   │   ├── validation.py       # 魔数校验、大小校验、device_id 校验
│   │   └── naming.py           # 相对路径生成
│   ├── services/
│   │   └── ingest.py           # 图片来源编排（应用层用例）
│   ├── infra/
│   │   ├── db.py               # 引擎与会话
│   │   ├── tables.py           # 表定义
│   │   ├── repository.py       # ImageRepository
│   │   └── storage.py          # 本地文件存储（原子写入）
│   └── migrations/             # 版本化迁移脚本
└── tests/
    ├── conftest.py
    ├── unit/
    └── integration/
```

### 3.3 关键设计决策

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-01 | 采用 FastAPI | 提供 pydantic 类型契约、自动 OpenAPI 文档、请求校验与依赖注入；Flask 需外挂 marshmallow + apispec 才能达到同等契约强度，等于自建一层 |
| ADR-02 | 项目级虚拟环境，不装全局 | 环境隔离与依赖锁定是商业级基线；同时避免污染本机 Anaconda |
| ADR-03 | 数据库选 SQLite | 单机、单写入者、数据量以每天几十张图增长，SQLite 足够且零运维；后续如需并发可平滑迁移 PostgreSQL |
| ADR-04 | 首选 SQLAlchemy 2.0 ORM + Alembic 迁移 | 表结构会随蜕皮记录、传感器读数扩展，版本化迁移是刚需；若目标 Python 版本无可用 wheel，降级为 stdlib `sqlite3` + 自研版本化迁移器，功能等价，记入 ADR |
| ADR-05 | 同步数据访问，路由声明为 `def` | 单机低并发，同步实现更少陷阱；FastAPI 会将同步路由放入线程池，不阻塞事件循环 |
| ADR-06 | 日志用 stdlib `logging` + 自写 JSON 格式化器 | 满足结构化日志需求且零额外依赖；`contextvars` 承载 request_id |
| ADR-07 | 图片原样存盘，不重编码 | 后续算法依赖亮度与饱和度，重编码会引入不可控的颜色偏移，污染信号 |

---

## 4. 数据模型

### 4.1 表 `images`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 | UUID v4 |
| `device_id` | TEXT | 非空，索引 | 设备标识，缺省 `unknown` |
| `rel_path` | TEXT | 非空，唯一 | 相对数据根目录的路径，统一用 `/` 分隔 |
| `byte_size` | INTEGER | 非空，> 0 | 字节数 |
| `sha256` | TEXT | 非空，**唯一索引** | 内容哈希，幂等键 |
| `captured_at_utc` | TEXT | 非空 | 抓拍时间，ISO 8601 UTC |
| `local_date` | TEXT | 非空，索引 | `YYYY-MM-DD`，按配置时区换算 |
| `received_at_utc` | TEXT | 非空 | 服务端接收时间，ISO 8601 UTC |

复合索引 `(local_date, device_id, captured_at_utc)` 支撑「某设备某天的时序列表」这一主查询。

### 4.2 迁移策略

- 迁移脚本按序号命名，向前单向递增，每步可独立执行
- 服务启动时校验 `schema_version`，不匹配则拒绝启动并提示执行迁移
- 不使用自动建表（`create_all`）替代迁移，避免生产环境 schema 漂移

---

## 5. 存储布局

```text
<SHEDGUARD_DATA_DIR>/
├── shedguard.db
└── images/
    └── 2026-11-02/
        └── eye-01/
            ├── 143005_a1b2c3d4.jpg
            └── 143005_9f8e7d6c.jpg
```

- 文件名格式：`HHMMSS_<sha256 前 8 位>.<扩展名>`
- 扩展名由**魔数**决定，不采信客户端文件名
- 写入采用「临时文件 + 原子重命名」，避免半截文件被后续分析读到
- 若目标路径已存在且内容哈希一致，视为幂等命中，不重写

---

## 6. API 契约

所有接口前缀 `/api/v1`。响应统一 `application/json`，取图接口除外。

### 6.1 上传

```http
POST /api/v1/images
Content-Type: multipart/form-data | image/jpeg | image/png
X-Device-Id: eye-01
X-Captured-At: 2026-11-02T06:30:05Z
```

| 请求头 | 必填 | 说明 |
|---|---|---|
| `X-Device-Id` | 否 | 缺省 `unknown`；须匹配 `^[A-Za-z0-9_-]{1,64}$` |
| `X-Captured-At` | 否 | RFC 3339；缺省取服务端接收时间 |

`multipart/form-data` 形态取字段名 `file`；`image/*` 形态直接读原始 body，供 ESP32 侧省内存使用。

响应 `201 Created`（新建）或 `200 OK`（幂等命中）：

```json
{
  "id": "5f1c2a9e-7b3d-4c8a-9e21-0d6b4f2a8c11",
  "device_id": "eye-01",
  "rel_path": "images/2026-11-02/eye-01/143005_a1b2c3d4.jpg",
  "byte_size": 48213,
  "sha256": "a1b2c3d4e5f6...",
  "captured_at_utc": "2026-11-02T06:30:05+00:00",
  "local_date": "2026-11-02",
  "received_at_utc": "2026-11-02T06:30:07.412+00:00",
  "duplicate": false
}
```

### 6.2 列表

```http
GET /api/v1/images?date=2026-11-02&device_id=eye-01&limit=100&offset=0
```

```json
{
  "items": [ { "id": "...", "rel_path": "...", "captured_at_utc": "..." } ],
  "total": 12,
  "limit": 100,
  "offset": 0
}
```

`limit` 上限 500，缺省 100；`date` 缺省为服务端当前本地日期（按 `SHEDGUARD_TIMEZONE` 换算）。

### 6.3 取图

```http
GET /api/v1/images/{id}
```

返回原始字节，`Content-Type` 按入库时的魔数判定结果，附 `ETag`（即 sha256）与 `Cache-Control: immutable`。

`GET /api/v1/images/{id}/metadata` 返回单条元数据 JSON。

### 6.4 健康检查

| 接口 | 语义 |
|---|---|
| `GET /healthz` | 进程存活，恒 200 |
| `GET /readyz` | 依赖就绪：数据目录可写、数据库可读；不满足返回 503 |

---

## 7. 错误契约

统一结构：

```json
{
  "error": {
    "code": "UNSUPPORTED_MEDIA_TYPE",
    "message": "仅支持 JPEG 与 PNG 图片",
    "request_id": "01JC3F4M2N8PQR7T"
  }
}
```

| 错误码 | HTTP | 触发条件 |
|---|---|---|
| `INVALID_REQUEST` | 400 | 参数格式错误、时间戳不可解析 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 魔数既非 JPEG 也非 PNG |
| `PAYLOAD_TOO_LARGE` | 413 | 超出 `SHEDGUARD_MAX_UPLOAD_BYTES` |
| `EMPTY_PAYLOAD` | 400 | 请求体为空 |
| `NOT_FOUND` | 404 | 记录不存在 |
| `STORAGE_UNAVAILABLE` | 503 | 磁盘写入失败或空间不足 |
| `INTERNAL_ERROR` | 500 | 未预期异常，日志中保留堆栈，响应不泄露内部细节 |

`request_id` 同时通过响应头 `X-Request-Id` 返回，便于比对日志。

---

## 8. 幂等与并发

1. 先按 `sha256` 查询，命中则直接返回既有记录，`duplicate: true`
2. 未命中则落盘后插入记录
3. 并发上传同一图片时，唯一索引兜底：捕获唯一约束冲突，回查后按幂等命中返回
4. 落盘先于入库；入库失败时清理已写入的文件，避免产生孤儿文件

`duplicate` 语义仅限于「同一内容已存在」，不代表请求失败。

---

## 9. 安全与输入校验

- 大小上限默认 10 MiB，可配置。优先依据 `Content-Length` 在读取 body 前拒绝；对未声明长度或声明不实的分块传输，流式读取时累计计数并中途中断。两种情况均返回 413，不将整个 body 读入内存后再判断
- 魔数校验：JPEG `FF D8 FF`，PNG `89 50 4E 47 0D 0A 1A 0A`
- 不做图片解码验证：解码会引入解析攻击面（解码炸弹、超大像素），而本项目只需判定「是否为图片内容」，魔数校验已满足目标
- `device_id` 白名单字符，防止路径穿越
- 路径完全由服务端生成，不接受客户端提供的文件名或子路径
- 数据库访问全部参数化，禁止字符串拼接 SQL
- 默认监听 `127.0.0.1`；固件联调需显式设为 `0.0.0.0`，README 中标注该操作的风险

---

## 10. 可观测性

- `request_id` 由中间件在请求入口生成（ULID 风格，26 位字符），写入 `contextvars`，日志与响应头共用同一值
- 请求日志字段：`request_id`、`method`、`path`、`status`、`duration_ms`、`device_id`、`byte_size`
- 日志格式：生产为单行 JSON，开发可切 `console` 便于阅读
- 启动日志记录生效配置（脱敏后）、数据库路径、监听地址
- 异常日志保留完整堆栈，响应体只给错误码与 request_id

---

## 11. 配置项

| 环境变量 | 缺省值 | 说明 |
|---|---|---|
| `SHEDGUARD_DATA_DIR` | `./data` | 数据根目录 |
| `SHEDGUARD_DB_URL` | `sqlite:///<data>/shedguard.db` | 数据库连接 |
| `SHEDGUARD_HOST` | `127.0.0.1` | 监听地址 |
| `SHEDGUARD_PORT` | `8000` | 监听端口 |
| `SHEDGUARD_MAX_UPLOAD_BYTES` | `10485760` | 单图大小上限 |
| `SHEDGUARD_TIMEZONE` | `Asia/Shanghai` | 日期分片所用时区 |
| `SHEDGUARD_LOG_LEVEL` | `INFO` | 日志级别 |
| `SHEDGUARD_LOG_FORMAT` | `json` | `json` 或 `console` |

配置全部经 pydantic-settings 校验，非法值在**启动时**即抛出可读错误并退出，不允许带病运行。

---

## 12. 测试策略

| 层次 | 范围 | 手段 |
|---|---|---|
| 单元 | 魔数校验、大小校验、device_id 校验、路径生成、时区换算、幂等分支 | 纯函数，无 IO |
| 集成 | 完整请求链路：上传、幂等、列表、取图、错误码 | `TestClient` + 临时目录 + 临时 SQLite，每个用例独立隔离 |
| 冒烟 | 真实服务启动后 `curl` 上传 | 手动执行，命令固化进 README |

- 覆盖率门槛：总体 ≥ 85%，`domain/` 与 `services/` ≥ 90%
- 测试不得依赖网络、不得写入仓库内固定目录

---

## 13. 工程工具链

| 工具 | 用途 | 配置要点 |
|---|---|---|
| `ruff` | Lint 与格式化 | 行宽 100，规则集 `E,F,I,UP,B,SIM,RUF` |
| `mypy` | 静态类型检查 | `strict`；第三方缺桩项按白名单局部豁免，禁止全模块 `ignore` |
| `pytest` | 测试与覆盖率 | `--cov`，门槛写入配置 |
| `pre-commit` | 提交前拦截 | ruff、mypy、行尾与文件结尾规范化 |
| GitHub Actions | CI | lint、类型、测试三步；Python 3.12 与 3.13 双版本矩阵 |

依赖以 `pyproject.toml` 声明，`requirements.lock` 锁定，两者同时入库。

---

## 14. 实施里程碑

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| M1 | 骨架、配置、日志、错误契约、健康检查 | 服务能起，`/healthz` 与 `/readyz` 通过，配置错误时给出可读报错 |
| M2 | 上传、落盘、幂等、查询、取图 | 五条核心验收全部通过 |
| M3 | 工具链、CI、覆盖率达标 | 本地与 CI 命令一致且全绿 |
| M4 | 文档、ADR、交接文档更新 | README 可按步骤跑通，`docs/handoff.md` 同步 |

每个阶段独立提交，保持原子性。

---

## 15. 验收标准

1. `pytest` 全部通过，覆盖率 ≥ 85%
2. `ruff check` 与 `ruff format --check` 无差异
3. `mypy` 严格模式无错误
4. `curl` 上传真实 JPG：文件落盘、数据库有记录、`GET /api/v1/images/{id}` 取回的 sha256 与原图一致
5. 同一图片重复上传：返回 200 且 `duplicate: true`，数据库记录数不变
6. 非图片内容返回 415；超出上限返回 413；非法 `device_id` 返回 400
7. `python -m shedguard_server` 可启动；配置非法时启动即失败并给出明确提示
8. 日志为单行 JSON 且含 `request_id`，与响应头 `X-Request-Id` 一致
9. CI 工作流文件存在，本地可执行与 CI 相同的三条命令
10. README 能让人从零跑通，不依赖机器绝对路径

---

## 16. 已知欠账

以下项目经明确决策**本轮不做**，在进入真实用户阶段前必须补齐，在此登记以免遗忘：

| 欠账 | 风险 | 补齐时点 |
|---|---|---|
| 无鉴权 | 局域网内任何主机可上传图片 | 公网或多人使用前 |
| 无 HTTPS | 图片明文传输 | 同上，由反向代理终止 |
| 无数据留存与删除策略 | 家庭画面长期留存，隐私合规缺口 | 真实用户数据进入前 |
| 无磁盘配额与清理 | 数据目录可被写满 | 连续采集稳定后 |
| 无限流 | 单机易被打满 | 公网部署前 |
| 无备份 | 磁盘故障即数据丢失 | 有真实数据积累后 |
| 存储未加密 | 拿到磁盘即可读图 | 与隐私策略一并处理 |

---

## 17. 实施风险

| 风险 | 应对 |
|---|---|
| Python 3.14 生态兼容性 | 优先用 3.12 / 3.13 建虚拟环境；若依赖无可用 wheel，按 ADR-04 降级数据访问实现并记录 |
| 沙箱限制 pip 临时目录 | 将 pip 的临时目录与缓存指向项目内可写路径 |
| 本机无全局 `python` 命令 | README 说明需自行指定解释器，不写死绝对路径 |

---

## 18. 待确认事项

1. 技术栈最终确认：FastAPI + SQLAlchemy + Alembic（含 ADR-04 降级路径）
2. 接口前缀是否采用 `/api/v1`（当前设计）
3. 缺省监听 `127.0.0.1`，固件联调时改 `0.0.0.0`，是否接受这一手动切换

以上确认后进入实现计划与 TDD 开发。
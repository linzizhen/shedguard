# shedguard-server

爬宠蜕皮预警系统的后端图片接入服务。负责接收设备上传的照片、按日期与设备归档、把元数据写入 SQLite，并为后续的每日对比分析提供查询接口。

设计依据见 [`../docs/specs/2026-11-02-server-image-ingest-design.md`](../docs/specs/2026-11-02-server-image-ingest-design.md)。

## 当前进度

M1（工程骨架）已完成：配置校验、结构化日志、统一错误契约、健康检查。

## 运行

```powershell
# 在仓库根目录
.\.venv\Scripts\python.exe -m pip install -r server\requirements.lock

# 启动服务（默认 127.0.0.1:8000）
$env:PYTHONPATH = "server\src"
.\.venv\Scripts\python.exe -m shedguard_server
```

检查存活与就绪：

```powershell
curl.exe http://127.0.0.1:8000/healthz
curl.exe http://127.0.0.1:8000/readyz
```

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

## 开发

```powershell
cd server
..\.venv\Scripts\python.exe -m pytest --cov=shedguard_server --cov-report=term-missing
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m mypy
```

覆盖率门槛见 `pyproject.toml`，业务层（`domain`、`services`）要求更高。

## 目录结构

```
server/
  pyproject.toml        项目配置与工具链
  requirements.txt      运行期依赖
  .env.example          配置样例
  src/shedguard_server/
    app.py              应用装配
    config.py           配置模型
    errors.py           错误契约
    logging_setup.py    结构化日志
    api/routes/         HTTP 路由
  tests/
    unit/               领域与工具层
    integration/        HTTP 端到端
```
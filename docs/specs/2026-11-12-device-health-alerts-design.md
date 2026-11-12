# 设备健康兜底提醒（P17）设计

> 状态：草案，待批准
> 关联：`docs/plan.md` P17；需求来源 m07368「逐一修复即可」中的问题⑤「静默失败」

## 1. 要解决的问题

当前只有「检测到蜕皮」才提醒。于是产生一个误导：**没收到提醒，用户会以为一切正常**。但实际可能是：

1. 设备断电、断网、程序卡死 —— 一张图都没上传；
2. 设备在拍，但守宫躲起来或被遮挡 —— 一直拍不到有效目标，判定永远是 `unknown`。

这两种情况下用户什么都收不到，问题会被拖到下一次蜕皮失败才暴露。P17 要给这两种「沉默」加上显式提醒。

## 2. 范围

做：

- 设备静默检测：设备在**活跃时段内**连续超过阈值时长没有新上传 → 生成「设备可能离线」提醒。
- 无有效画面检测：同一设备连续 N 次上传都**未检出守宫** → 生成「看不到守宫」提醒。
- 两类提醒复用现有 `alerts` 表与推送通道，App 的提醒横幅按 `kind` 显示不同文案。

不做：

- 不做设备端心跳接口（固件不改）。
- 不做短信/邮件兜底、不做多级升级策略。
- 不做夜间静默判定（夜间本就不抓拍）。

## 3. 提醒类型扩展

`alerts.kind` 取值从 1 个扩到 3 个：

| kind | 触发 | 文案（推送标题 / 正文） |
|---|---|---|
| `shedding_detected` | 状态跃迁到 shedding（已有） | 守宫正在蜕皮 / 检测到蜕皮白皮，请打开照片查看 |
| `device_silent` | 活跃时段内超时无上传 | 设备可能离线 / 已经 N 小时没收到照片，请检查电源与网络 |
| `no_detection` | 连续 N 次未检出守宫 | 看不到守宫 / 连续 N 张照片没拍到守宫，请调整机位 |

唯一键沿用 `(device_id, local_date, kind)`：同一设备同一天同一类提醒只建一条，天然去重。冷却仍用 `SHEDGUARD_ALERT_COOLDOWN_HOURS`。

`AlertRow.state` 对非蜕皮类提醒写空串 `""`，`image_id` 可空；`confidence` 为空。

## 4. 判定规则（纯函数，便于单测）

新增 `server/src/shedguard_server/domain/health.py`：

```python
@dataclass(frozen=True, slots=True)
class DeviceHealthInput:
    device_id: str
    now: datetime                  # 当前时刻（UTC）
    last_upload_at: datetime | None
    recent_detections: tuple[bool, ...]   # 最近若干次上传是否检出守宫，新→旧
    capture_start_hour: int
    capture_end_hour: int
    timezone: str

@dataclass(frozen=True, slots=True)
class HealthFinding:
    kind: str                      # device_silent / no_detection
    detail: str                    # 人类可读，用于推送正文
```

`evaluate_device_health(data, *, silence_hours=6, no_detection_streak=5) -> list[HealthFinding]`：

1. **静默**：把 `now` 转到设备时区；只有落在 `capture_start_hour`–`capture_end_hour` 内才判定。若 `last_upload_at` 为空（从未上传）→ 跳过（避免设备从未配置就报警）。若 `now - last_upload_at > silence_hours` 且现在处于活跃时段 → `device_silent`。
2. **无有效画面**：`recent_detections` 取最近 `no_detection_streak` 条，若数量够且全为 False → `no_detection`。
3. 20:00 之后与 08:00 之前不报静默（正常不拍）。

## 5. 扫描触发

FastAPI `lifespan` 启动一个后台 asyncio 任务，每 `SHEDGUARD_HEALTH_SCAN_MINUTES`（默认 10）分钟：

1. 列出 `push_devices` 中出现过的 `device_id`（去重）；
2. 对每个设备查 `images` 最近一条 `captured_at_utc`、最近 N 条 `shedding_states` 是否有 box/state；
3. 调 `evaluate_device_health`；
4. 对每条 finding 用 `AlertService.create_for_transition` 的同款去重 + `deliver` 发送。

新增配置：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SHEDGUARD_HEALTH_MONITOR_ENABLED` | `true` | 是否启动后台扫描；测试与本地调试可关 |
| `SHEDGUARD_HEALTH_SCAN_MINUTES` | `10` | 扫描周期（1–1440） |
| `SHEDGUARD_DEVICE_SILENCE_HOURS` | `6` | 活跃时段内多久没上传算静默（1–48） |
| `SHEDGUARD_NO_DETECTION_STREAK` | `5` | 连续多少次未检出算异常（2–20） |

`AlertService` 增加通用入口 `create_alert(*, device_id, local_date, kind, pet_id=None, state="", image_id=None, confidence=None, now=None) -> Alert | None`，`create_for_transition` 改为调用它（保持既有行为不变）。

## 6. 接口与 App

- `GET /api/v1/alerts` 已返回 `kind`，无需改契约；按用户隔离沿用现有 owner 过滤。
- App：
  - `log.tsx` 的 `ALERT_STATE_LABEL` 改为按 `kind` 优先取文案，新增 `device_silent` / `no_detection` 两条；
  - 非蜕皮类提醒没有原图，详情页显示「这条提醒没有照片」而不是空图；
  - 详情页的「判定/置信度」两行对非 shedding 类隐藏。

## 7. 测试与验收

单元（`tests/unit/test_health.py`，纯函数，覆盖边界）：

1. 活跃时段内超时 → 1 条 `device_silent`；
2. 夜间超时不报；
3. 从未上传不报；
4. 未超时不报；
5. 连续 N 次未检出 → 1 条 `no_detection`；不足 N 次不报；中间有一次检出则清零。

集成（`tests/integration/test_health_api.py`）：

6. 造一台设备：`push_devices` 有记录、`images` 是 7 小时前的（在活跃时段内），手动触发一次扫描 → `GET /alerts` 出现 1 条 `device_silent`；
7. 再触发一次扫描 → 仍 1 条（唯一键去重）；
8. 关闭 `health_monitor_enabled` 时后台任务不启动（app.state 上无任务），扫描手动调也不建重复。

验收：覆盖率 ≥85%（业务层 ≥90%）、`ruff` 与 `mypy src tests` 全绿、既有 353 测试不回归。

## 8. 已知限制

1. 后台任务与进程同生共死：进程重启期间不会扫描，重启后补扫一次。
2. 单进程假设：多副本部署会重复扫描（唯一键保证不重复建 alert，但会重复发推送）。
3. 固件无心跳接口，只能靠「有没有新图」间接判断。
4. 夜间静默不判定；如后续启用红外再调整。

## 9. 实现记录（P17，2026-11-12）

落地文件：

| 层 | 文件 |
|---|---|
| 领域 | `domain/health.py`（`DeviceHealthInput` / `HealthFinding` / `evaluate_device_health`）；`domain/alerts.py` 新增 `ALERT_KIND_DEVICE_SILENT`、`ALERT_KIND_NO_DETECTION` |
| 服务 | `services/health.py` 的 `scan_once(...)`；`services/alerts.py` 新增通用 `create_alert(...)`，`create_for_transition` 改为委托它，`MESSAGES` 按 kind 取推送标题/正文 |
| 仓储 | `SheddingStateRepository.recent_detections`、`ImageRepository.latest_captured_at`、`PushDeviceRepository.list_device_ids` |
| 装配 | `app.py` 的 `_health_loop` + lifespan 内 `asyncio.create_task`，关闭时 cancel |
| 配置 | `health_monitor_enabled`、`health_scan_minutes`、`device_silence_hours`、`no_detection_streak`、`capture_start_hour`、`capture_end_hour` |
| App | `log.tsx` 按 kind 取横幅文案、无照片时显示图标占位；`alert/[id].tsx` 非蜕皮类隐藏判定/置信度并提示「这条提醒没有照片」 |

与规格的偏差（2 条）：

| # | 规格原写 | 实际实现 | 原因 |
|---|---|---|---|
| 1 | 活跃时段取自既有配置 | 新增 `capture_start_hour` / `capture_end_hour` 两个配置 | 原有 `capture_hour` 是「代表帧目标时刻」，语义不同 |
| 2 | 集成测试文件 `test_health_api.py` | `test_health_alerts_api.py`，单测 `test_health_domain.py` | 仓库已有 `tests/integration/test_health.py`（健康检查），同名会触发 pytest 导入冲突 |

验收结果：365 测试全部通过（新增 12 条：8 条纯函数 + 4 条集成）、覆盖率 **95.94%**；`ruff` 与 `mypy src tests`（108 文件）全绿。集成测试验证：7 小时无上传（活跃时段内）→ 生成 1 条 `device_silent`；重复扫描不重复建；1 小时前有上传不报；监控关闭时启动不创建后台任务。

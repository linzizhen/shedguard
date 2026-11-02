# 时序输入层设计（M3）

> 状态：待批准
> 日期：2026-11-02
> 上游：`docs/specs/2026-11-02-server-image-ingest-design.md`（M1/M2，已实现）
> 下游：Phase 5 图像分析管线、Phase 6 判定规则

## 1. 背景

M2 已经能收图：上传、sha256 幂等、按天归档、按天分页查询、按 id 取原图。数据现在是「一堆按天归档的照片」。

判定链路需要的不是照片集合，而是三件事：

1. **每天恰好一条可比帧** —— 一天传了 5 张，分析层不知道该用哪张。
2. **连续的日期序列，缺失日可见** —— 逐个日期调 `/api/v1/images?date=` 是 N 次请求，且拿不到「这天没图」这个事实。
3. **哪些天是蜕皮日** —— 没有标注，Phase 6 的回测无从对齐。

这三件在现有接口里全部缺失。M3 就是把图片集合变成时序输入的中间层。

## 2. 目标

| 编号 | 目标 | 验收方式 |
|---|---|---|
| G1 | 提供确定、可解释的每日代表帧规则 | 同一批输入，重复调用结果一致 |
| G2 | 一次请求拿到区间内每天的帧与缺失标记 | 3 天区间返回 3 条，缺失日 `image_id` 为 null |
| G3 | 可记录与查询蜕皮事件 | 写入后可按设备与区间查回，重复写入幂等 |

## 3. 非目标

- 不做图像对齐、亮度归一化、特征提取（Phase 5）。
- 不做判定规则与阈值（Phase 6）。
- 不做提醒与推送（Phase 7）。
- 不做多设备聚合、不做多物种。
- 不做前端展示。

## 4. 每日代表帧规则

### 4.1 为什么必须固定时段

蜕皮前兆的信号（体表白度上升、眼部浑浊）在幅度上是**缓慢、小幅**的。同一只守宫在不同时段拍摄，光照色温、相机自动曝光、白平衡都会变化，这些变化量级往往大于蜕皮前兆本身。逐日对比的前提是「除了时间，其他变量尽量不变」。

固件稳定后，拍摄时刻是固定的。手机临时方案做不到严格固定，但至少要收敛到一个目标时刻附近。

### 4.2 规则

输入：某设备某一天的全部图片记录。

1. 目标时刻 = `SHEDGUARD_CAPTURE_HOUR`（默认 20）在 `SHEDGUARD_TIMEZONE` 下的当天时刻。
2. 窗口 = 目标时刻 ± `SHEDGUARD_CAPTURE_WINDOW_MINUTES`（默认 180 分钟）。
3. 候选 = 该设备当天（按 `local_date` 划分）的全部图片。
4. 选择：
   - 窗口内有候选 → 取距目标时刻最近的一张，`in_window = true`。
   - 窗口内无候选 → 取当天距目标时刻最近的一张，`in_window = false`。
   - 当天无候选 → 该日缺失。
5. 距离相同时取 `captured_at_utc` 较早的一张，保证确定性。

### 4.3 为什么窗口外也返回

丢弃会让「今天只有凌晨 3 点一张」变成缺失日，数据本来就稀疏，再丢就没了。正确做法是**标注而不是丢弃**：分析层默认只用 `in_window = true` 的帧，在数据不足时再决定是否降级使用窗口外的帧。

由消费方决定，比由采集方替它决定更诚实。

## 5. 数据模型

新增表 `shed_events`：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | 主键 | UUID v4 |
| `device_id` | TEXT | 非空 | 与 `images.device_id` 同规则 |
| `event_date` | TEXT | 非空 | `YYYY-MM-DD`，本地日期 |
| `outcome` | TEXT | 非空 | `completed` / `partial` / `stuck` / `unknown` |
| `notes` | TEXT | 可空 | 自由文本，长度上限 2000 |
| `created_at_utc` | TEXT | 非空 | ISO 8601 UTC |
| `updated_at_utc` | TEXT | 非空 | ISO 8601 UTC |

约束：

- 唯一索引 `uq_shed_events_device_date` on `(device_id, event_date)` —— 同一天同一设备只记一次，改主意就覆盖。
- 索引 `ix_shed_events_date` on `event_date`（按区间查）。

`outcome` 的含义：

- `completed`：整体蜕完，无残留。
- `partial`：蜕了大部分，脚趾或尾部有残留。
- `stuck`：卡皮，需要人工处理。
- `unknown`：事后补录，记不清细节。

## 6. 接口

### 6.1 `GET /api/v1/series`

查询设备在日期区间内的每日代表帧。

| 参数 | 必填 | 说明 |
|---|---|---|
| `device_id` | 是 | 设备标识 |
| `from` | 是 | 起始日期 `YYYY-MM-DD`（含） |
| `to` | 是 | 结束日期 `YYYY-MM-DD`（含） |

约束：`from <= to`，区间天数 ≤ 366，否则 400 `INVALID_REQUEST`。

响应 200：

```json
{
  "device_id": "cam-1",
  "from": "2026-11-01",
  "to": "2026-11-03",
  "days": [
    {
      "date": "2026-11-01",
      "image_id": "01JABCDEF...",
      "captured_at_utc": "2026-11-01T12:03:00+00:00",
      "in_window": true,
      "total_images": 3
    },
    {
      "date": "2026-11-02",
      "image_id": null,
      "captured_at_utc": null,
      "in_window": false,
      "total_images": 0
    }
  ],
  "total_days": 3,
  "missing_days": 1
}
```

`days` 按日期升序，**区间内每一天都出现**，无图日为 `image_id: null`。

### 6.2 `PUT /api/v1/shed-events/{device_id}/{event_date}`

记录或覆盖一次蜕皮事件。

请求体：

```json
{"outcome": "completed", "notes": "整体顺利，尾部有一小片残留"}
```

- `outcome` 必填，四选一。
- `notes` 可空，上限 2000 字符。

响应：新建 201，覆盖 200，响应体为事件对象，字段与 6.3 的 `items` 元素一致。

**为什么用 PUT 而不是 POST**：同一设备同一天在业务上只会蜕一次皮。用 PUT 让「补录笔误、改 outcome」变成一次幂等的覆盖，不会产生重复事件，也不需要为「已存在」设计 409 冲突码。

### 6.3 `GET /api/v1/shed-events`

| 参数 | 必填 | 说明 |
|---|---|---|
| `device_id` | 否 | 省略则查全部设备 |
| `from` | 否 | 起始日期（含） |
| `to` | 否 | 结束日期（含） |

响应 200：

```json
{
  "items": [
    {
      "id": "01J...",
      "device_id": "cam-1",
      "event_date": "2026-11-05",
      "outcome": "completed",
      "notes": "整体顺利",
      "created_at_utc": "2026-11-05T21:14:00+00:00",
      "updated_at_utc": "2026-11-05T21:14:00+00:00"
    }
  ],
  "total": 1
}
```

按 `event_date` 降序。不分页：蜕皮一年最多几十次，YAGNI。

## 7. 配置变更

新增 2 项，总数从 8 项变 10 项：

| 变量 | 默认值 | 校验 | 说明 |
|---|---|---|---|
| `SHEDGUARD_CAPTURE_HOUR` | `20` | 0–23 整数 | 目标拍摄时刻（本地时区） |
| `SHEDGUARD_CAPTURE_WINDOW_MINUTES` | `180` | 0–720 整数 | 目标时刻前后的匹配窗口 |

`SHEDGUARD_CAPTURE_HOUR` 的解释依赖 `SHEDGUARD_TIMEZONE`。

## 8. 错误处理

复用现有 7 个错误码，不新增：

| 场景 | 错误码 | HTTP |
|---|---|---|
| `from` / `to` 缺失或格式错 | `INVALID_REQUEST` | 400 |
| `from > to` | `INVALID_REQUEST` | 400 |
| 区间超过 366 天 | `INVALID_REQUEST` | 400 |
| `device_id` 不符合 `^[A-Za-z0-9_-]{1,64}$` | `INVALID_REQUEST` | 400 |
| `outcome` 不在枚举内 | `INVALID_REQUEST` | 400 |
| `notes` 超过 2000 字符 | `INVALID_REQUEST` | 400 |
| `event_date` 格式非法 | `INVALID_REQUEST` | 400 |

## 9. 测试计划

单元测试（`tests/unit/`）：

- `test_series.py`：代表帧选择的 8 个分支 —— 窗口内唯一、窗口内多张取最近、距离相同取较早、窗口外取最近、当天无图、多设备隔离、`in_window` 标注正确、跨时区边界。
- `test_events.py`：outcome 枚举校验、notes 长度、device_id 校验。

集成测试（`tests/integration/`）：

- `test_series.py`：3 天区间含 1 缺失日；区间参数非法 400；区间超限 400；device_id 非法 400。
- `test_shed_events.py`：PUT 新建 201、重复 PUT 覆盖 200 且 id 不变、GET 按设备与区间过滤、GET 无过滤返回全部、非法 outcome 400。

覆盖率目标不变：总体 ≥85%，`domain/` 与 `services/` ≥90%。

## 10. 验收

1. 上传 3 张不同时刻的图到同一天，`GET /series` 只返回 1 条，且是窗口内最近的那张。
2. `GET /series` 区间内每天都有条目，无图日 `image_id` 为 null。
3. `in_window` 反映真实情况：窗口外唯一一张返回 `false`。
4. 同一设备同一天 PUT 两次，第二次返回 200，`id` 不变，`notes` 被覆盖。
5. `GET /shed-events?device_id=X&from=A&to=B` 只返回区间内该设备的事件。
6. `from > to`、非法日期、超 366 天、非法 device_id 全部返回 400 `INVALID_REQUEST`。
7. ruff / mypy / pytest 全绿，覆盖率达标。
8. Alembic 迁移 `0002_shed_events` 可正向执行、可回滚。
9. 旧接口行为不变，现有 99 个测试全部仍通过。
10. 文档更新：`server/README.md` 接口表、`docs/handoff.md` 进度。

## 11. 已知欠账

- 代表帧规则只按时间收敛，不判断画面可用性（守宫是否入镜、是否模糊）。这需要 Phase 5 的图像质量门，本期不做。
- `shed_events` 没有「蜕皮开始日」与「蜕皮结束日」的区分，只记一天。真实场景里蜕皮可能跨 1–2 天，等有实际样本再决定是否拆分。
- 没有事件与图片的显式关联，靠 `event_date` 与 `local_date` 对齐。如果日后允许「床单日」与「照片日」不同，再引入显式外键。
- 无鉴权、无审计日志：与 M2 的欠账一致，整体推迟到 ADR 阶段。
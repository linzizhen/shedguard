# 蜕皮检测提醒链路设计规格（固件一期 + 服务端流水线 + 推送）

> 状态：**待用户审查批准**
> 日期：2026-11-11
> 上游决策：用户 m06123（不做蜕皮预测、改做蜕皮检测）、m06128（两者都要、分阶段；设备自动拍）、m06138（定时抓拍上传、服务端判定；推送走 Expo）
> 关联规格：`docs/specs/2026-11-09-app-and-firmware-design.md`（App 与固件总览，本文在其固件大纲上细化并新增提醒链路）

## 0. 背景与变更摘要

现有系统已经能「单张图判定蜕皮状态」（二态 `normal` / `shedding`，测试准确率 0.93）、能「按天推导蜕皮事件」，但缺一条**从设备到用户**的闭环：

- 设备不会自己拍、自己传；
- 图片传上来后，检测与状态判定要人手动触发接口；
- 判出来「正在蜕皮」也没有任何渠道告诉用户；
- App 里的「蜕皮预测」功能被用户正式放弃。

本期把这条链路补齐，并下线预测。

**放弃预测的理由**：预测需要同一个体多个完整蜕皮周期，四到六周才一周期的动物在现有数据下凑不出统计量；而「看到就提醒」是单张图分类，正是现有模型擅长的。

## 1. 目标与非目标

**目标（一期）**
1. ESP32-S3-EYE 定时抓拍并上传，无需人工干预。
2. 服务端收到新图后自动跑「检测 → 裁剪 → 状态分类」，落 `shedding_states`。
3. 当设备状态由「非蜕皮」跃迁为「蜕皮中」时，生成一条提醒并经 Expo 推送送到用户手机。
4. App 增加「提醒」列表与设备绑定，随手能看最近一次提醒与对应照片。

**非目标（一期不做）**
- 蒙白（opaque）检测——零样本，见第 11 节二期。
- 红外/夜间识别——模型无红外训练数据，一期只在照明时段抓拍。
- 多用户与鉴权、HTTPS、OTA、配网 UI——沿用既有欠账清单。

## 2. 产品行为变更：下线蜕皮预测

| 位置 | 处理方式 | 理由 |
|---|---|---|
| App 蜕皮日志屏的「预测窗口」卡片 | **移除** | 用户明确不做预测 |
| `GET /api/v1/pets/{pet_id}/shed-prediction` | 保留，标记 **Deprecated**，不再维护 | 不删接口以降低回归风险；App 不再调用 |
| `docs/handoff.md` / `app/README.md` | 同步说明预测已下线 | 交接一致性 |

## 3. 端到端架构

```
ESP32-S3-EYE ──(HTTP POST /api/v1/images, X-Device-Id, X-Captured-At)──▶ 服务端
                                                                          │
                                    收图成功（非重复）→ 后台任务：             │
                                    ① 体表指标 analysis                      │
                                    ② 检测→裁剪→状态分类 shedding           │
                                                                          ▼
                                              shedding_states 落库，状态=SHEDDING
                                                                          │
                                          状态跃迁（前一日非 SHEDDING）→ 生成 alert
                                                                          │
                                             查 push_devices → 调 Expo Push API
                                                                          ▼
                                                                    用户手机通知
                                                                          │
                                              App「提醒」列表（拉 /api/v1/alerts）
```

## 4. 固件规格（ESP32-S3-EYE / ESP-IDF）

复用 `2026-11-09` 规格第 6 节的骨架，按「定时抓拍、服务端判定」补齐细节：

1. **WiFi**：`menuconfig` 配置 SSID/密码（MVP 不做配网 UI）；断线自动重连，板载 LED 红色提示。
2. **对时**：SNTP 同步，失败时用上次时间并标记，重试。
3. **抓拍节奏**：默认每 **30 分钟** 一张，仅落在抓拍窗口内（默认 `08:00` 起 `720` 分钟，即 08:00–20:00）。参数化，便于现场调。窗口外休眠。
4. **拍照**：JPEG，约 640×480 / 质量 80（兼顾清晰度与上传体积）。
5. **补光**：**一期只在窗口内用可见光**；850 nm 红外仅保留硬件能力，**不入训练分布前不启用**（避免模型域偏移导致误判）。
6. **上传**：`POST /api/v1/images`，头 `X-Device-Id: esp32-eye-01`、`X-Captured-At: <ISO8601 Z>`；body 为裸 `image/jpeg` 或 multipart 字段 file。
7. **失败处理**：上传失败写入 SPIFFS 队列（最多 7 张），WiFi 恢复后按时间顺序补传；补传成功后删除本地。
8. **状态指示**：绿闪=正常、红=WiFi 断、蓝=上传中、黄=本地队列积压。
9. **幂等**：服务端按 sha256 去重，重复上传返回 200 且不重复处理，固件据此视为成功并清理。

## 5. 服务端自动处理流水线

新增「收图后自动处理」，避免再依赖人工调接口：

- 配置项 `SHEDGUARD_AUTO_PROCESS`（默认 `true`）：为真时，图片上传成功且**非重复**后，用 FastAPI `BackgroundTasks` 排一个后台任务：
  1. `AnalysisService.analyze(image_id)`（体表指标）；
  2. `SheddingService.analyze(image_id)`（检测→裁剪→分类）。
- 两步均**幂等**（已有 `(metrics_version, detector_name)` / `(state_version, classifier_name)` 键），重复执行安全。
- 模型未配置时：跳过对应步骤并记结构化日志，不阻断上传；`/readyz` 已能反映模型缺失。
- 失败隔离：后台任务异常只记日志，绝不影响已经返回给设备的上传响应。

## 6. 提醒事件与去重规则

- **触发条件**：`SheddingService.analyze` 写入当日状态为 `SHEDDING`，且该设备**上一个有状态的日子不是** `SHEDDING`（即一次真实的「开始蜕皮」跃迁）。
- **去重键**：`(device_id, local_date, kind="shedding_detected")`，唯一索引；同日重复判定不重复建 alert。
- **冷却**：同设备 24 小时内最多推送一次（防止状态抖动刷屏）。
- 明确**不触发**的情况：状态为 `normal` / `opaque` / `unknown`；低置信度降级为 `unknown` 的帧。

## 7. 数据模型增量（迁移 `0005`）

新增两张表：

**`push_devices`**（推送目标）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | uuid |
| device_id | TEXT | 与图片同一设备标识，可空（纯 App 用户） |
| pet_id | TEXT FK pets.id ON DELETE SET NULL | 关联宠物 |
| expo_push_token | TEXT UNIQUE | ExpoPushToken |
| platform | TEXT | ios / android |
| created_at_utc / updated_at_utc | TEXT | ISO8601 |

**`alerts`**（提醒事件）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | uuid |
| device_id | TEXT | 设备 |
| pet_id | TEXT FK pets.id ON DELETE SET NULL | 宠物，可空 |
| kind | TEXT | `shedding_detected` |
| local_date | TEXT | YYYY-MM-DD |
| state | TEXT | 触发时状态 |
| image_id | TEXT | 触发帧 |
| confidence | REAL | 可空 |
| created_at_utc | TEXT | |
| delivered_at_utc | TEXT | 推送成功时间，可空 |
| push_status | TEXT | `pending` / `sent` / `failed` / `skipped` |

唯一索引 `ux_alerts_device_date_kind (device_id, local_date, kind)`。

## 8. 推送实现（Expo）

- **注册**：App 用 `expo-notifications` 取 `ExpoPushToken`，`POST /api/v1/devices` 上报 `{device_id?, pet_id?, expo_push_token, platform}`；同 token 重复注册做 upsert。
- **发送**：服务端 `PushService` 调 `https://exp.host/--/api/v2/push/send`，body `[{to, title, body, data:{alert_id, image_id}}]`。
  - 成功：`push_status=sent`，写 `delivered_at_utc`。
  - `DeviceNotRegistered`：标记 token 失效（`drop token`），`push_status=failed`。
  - 网络失败：`push_status=failed`，不重试超过 3 次。
- **可测性**：`PushService` 抽象为 Protocol，测试注入假实现；生产实现用 `httpx`（`trust_env=False`）。
- **降级**：即使推送失败，App 打开「提醒」列表仍能拉到未读 alert（拉模型兜底）。

## 9. API 清单

**新增**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/devices` | 注册/更新推送 token |
| DELETE | `/api/v1/devices/{id}` | 注销 |
| GET | `/api/v1/alerts?device_id=&pet_id=&limit=` | 提醒列表（按时间倒序） |
| PATCH | `/api/v1/alerts/{id}` | 标记已读 `{read: true}` |

**变更**
- `POST /api/v1/images`：成功后自动触发后台处理（行为增强，响应契约不变）。
- `GET /api/v1/pets/{pet_id}/shed-prediction`：标记 Deprecated。

## 10. App 改动

1. **移除**日志屏「预测窗口」卡片与其 hook（`useShedPrediction`）。
2. **新增「提醒」入口**：可在日志屏顶部显示最近一条 alert 卡片（时间、状态、缩略图），点进看原图。
3. **通知**：`expo-notifications` 注册 token → 上报；前台收到时刷新提醒列表。
4. **设备绑定**：设置屏增加「设备」卡片，填 `device_id` 并绑定到某宠物（写入 `/api/v1/devices`）。

## 11. 蒙白二期（数据飞轮）

- 一期所有上传帧已按设备/日期归档到 `data/images/`，无需额外改造即为候选池。
- 新增离线标注流程（复用 `ml/review_collected.py` 的 CSV 模式）：`ml/label_opaque.py` 生成待标注清单 → 人工标 `normal/opaque/shedding` → 攒够后训三分类，导出新 `labels.json`，服务端**不改代码**只换文件。
- 触发条件：累计人工标注的 `opaque` 样本 ≥ 150 张（经验下限）再启动三分类训练，避免类别极不平衡。

## 12. 验收标准

**固件**
- [ ] 上电 → 连 WiFi → NTP 对时 → 窗口内每 30 分钟抓拍上传 → 服务端收到图
- [ ] WiFi 断连恢复后能补传本地队列
- [ ] 窗口外不抓拍

**服务端**
- [ ] 上传新图后自动完成指标与状态两步，无需手工调接口
- [ ] 状态跃迁生成 alert，同日不重复；冷却 24h 生效
- [ ] 重复上传（同 sha256）不重复处理、不重复建 alert
- [ ] 模型未配置时上传仍成功，日志可诊断
- [ ] 新增代码覆盖率 ≥ 90%，ruff + mypy 全绿

**推送**
- [ ] 注册 token 后，模拟触发 alert，Expo 收到推送请求；失败不影响主流程
- [ ] `DeviceNotRegistered` 能清理失效 token

**App**
- [ ] 预测卡片已移除
- [ ] 「提醒」列表能展示 alert 与缩略图
- [ ] 设置屏可绑定设备到宠物

## 13. 风险与已知欠账

- **夜间/红外**：无红外训练数据，一期只在照明窗口抓拍；夜间蜕皮检测不到（后续补红外数据再议）。
- **域偏移**：模型训练在公开可见光微距图，真实饲养箱机位、玻璃反光、距离未知；上线初期误报需现场校准阈值。
- **推送依赖外网**：Expo Push 需要服务端能访问外网；纯局域网部署时推送不可用，靠 App 拉取兜底。
- **无鉴权**：任何人知道 `device_id` 都能上传，局域网内可接受。
- **单机位**：一只箱子一台设备；多箱需多设备多 `device_id`，未做管理 UI。

## 14. 实施顺序

1. 服务端：迁移 `0005` + `alerts`/`push_devices` 仓储 + `PushService` 抽象。
2. 服务端：收图自动流水线 + alert 生成规则 + 新 API（含测试）。
3. 固件：WiFi/NTP/定时抓拍/上传/补传队列（ESP-IDF 骨架）。
4. App：移除预测 + 提醒列表 + 通知注册 + 设备绑定。
5. 联调：真机抓拍 → 自动分类 → 推送 → App 展示。
6. 文档与提交。

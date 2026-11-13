# 守宫萌照（近景选片）设计

- 状态：草案，待批准
- 日期：2026-11-13
- 关联：`docs/plan.md` P25（本文）、P26（偏好打分器，后置）
- 上游：`docs/specs/2026-11-11-shedding-alert-pipeline-design.md`（抓拍与提醒链路）

## 1. 目标

让饲养箱每天自动给主人发一张「守宫的好照片」，并顺带把真实饲养箱照片沉淀成数据池。

三个明确收益：

1. 留存：蜕皮提醒一个月只有几次，萌照每天都有，App 才有打开理由。
2. 数据：系统当前一张真实机位照片都没有，模型全靠网图训练；用户每天产出的照片是后续校准与蒙白三态的唯一来源。
3. 传播：带水印的分享图就是获客入口。

## 2. 非目标

- 不做「用户上传照片、我们精修成大片」的图像生成服务。
- V1 不保证「一定是头部特写」——见 §3 的三阶段。
- 不做视频、不做连拍动画、不做自动发到社交平台（只做保存与系统分享）。

## 3. 三阶段（先能用，再变好）

| 阶段 | 内容 | 前置数据 | 产出 |
|---|---|---|---|
| **V1（本次）** | 「近景优先」选片：只在守宫占画面足够大时出图，按清晰度与占比打分选当天最佳；方形裁切；`换一张` / `这张好看` 收集偏好 | 无 | 可用功能 + 偏好数据 |
| **V2** | 用 V1 的偏好数据训「构图打分器」（liked vs skipped 二分类），替换 V1 的启发式打分 | 每只宠物 ≥ 50 次反馈 | 选片更接近人觉得好看 |
| **V3** | 若 V2 仍不够「头部特写」，补头部标注集训小检测头 | 300+ 头部框 | 真正的大头特写 |

**V1 的诚实边界**：能不能拍到头，取决于守宫愿不愿意凑近镜头。V1 保证的是「不糊、不小、主体清楚」，不保证「一定是脸」。

## 4. 数据模型（迁移 `0008_portraits.py`）

### 4.1 `portrait_shots`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(36) PK | UUID |
| `device_id` | String(64) 索引 | 来源设备 |
| `pet_id` | String(36) 可空 FK pets | 归属宠物（设备未绑宠物时为空） |
| `local_date` | Date | 本地日期 |
| `slot` | Integer | 当天第几张（0 起） |
| `image_id` | String(36) FK images | 原图 |
| `crop_path` | String(255) | 相对 `data/portraits/` 的路径 |
| `width` / `height` | Integer | 成品尺寸（方形） |
| `score` | Float | 选片得分 |
| `subject_ratio` | Float | 主体占画面比例 |
| `sharpness` | Float | 清晰度（边缘密度） |
| `created_at_utc` | String(40) | 生成时间 |

唯一约束：`(device_id, local_date, slot)`。

### 4.2 `portrait_feedback`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(36) PK | UUID |
| `shot_id` | String(36) FK portrait_shots | 被评价的成品 |
| `user_id` | String(36) FK users | 评价人 |
| `kind` | String(16) | `like` / `skip` / `crop_head` |
| `payload_json` | Text 可空 | `crop_head` 时的头部框（归一化坐标） |
| `created_at_utc` | String(40) | |

`skip` 同时驱动「换一张」：服务端在同一天剩余候选里取下一张，写新的 `slot`。

### 4.3 `portrait_settings`

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `pet_id` | String(36) PK FK pets | — | 一只宠物一份设置 |
| `enabled` | Boolean | true | 总开关 |
| `per_day` | Integer | 1（0–6） | 每天发几张 |
| `start_hour` | Integer | 17（0–23） | 投递时段起 |
| `end_hour` | Integer | 20（0–23） | 投递时段止，可跨午夜 |
| `updated_at_utc` | String(40) | | |

## 5. 选片算法（V1）

输入：某设备某天的全部图片及其 `frame_metrics`（已有检测框、置信度、`edge_density`、`lightness_mean`、`high_light_ratio`）。

**硬门槛**（任一不满足即候选出局）：

1. `detected = true` 且 `detector_confidence >= 0.45`；
2. `subject_ratio = box 面积 / 画面面积`，要求 `>= 0.10`（太远的不算近景）；
3. `sharpness(edge_density) >= 中位数 × 0.8`（当天相对比较，避免绝对阈值受光照影响）；
4. `high_light_ratio <= 0.35`（玻璃反光/曝光过度剔除）。

**打分**：

```
score = 0.45 × min(subject_ratio / 0.35, 1)
      + 0.35 × min(sharpness / p90_sharpness, 1)
      + 0.20 × center_score（框中心离画面中心越近越高）
```

**去重**：与当天已选出的成品做 dHash 比对（阈值 6），太像就换下一张，避免「每天同一张姿势」。

**裁切**：以检测框为中心，边长 = `max(box_w, box_h) × 1.35`，不足处贴边补齐；输出 1:1、长边 640、JPEG 质量 88。

## 6. 生成时机

不新增抓拍频率。服务端在每次上传后的处理流水线里顺带评估（复用 `process_image` 已算好的指标），满足门槛就把候选记进内存/临时表；到投递时刻再从当天候选里选最终成品并落盘。

为控制复杂度，V1 采用**投递时选片**：定时任务在投递时刻扫描当天该设备的图片，现算候选、选出最佳、生成成品。当天没有合格候选 → 不发送，App 显示「今天它躲起来了」。

## 7. 投递

复用现有提醒链路：新增 `ALERT_KIND_PORTRAIT = "portrait_ready"`，`state=""`、`image_id` 指向成品所属原图、`confidence` 为空。这样推送、提醒列表、已读、去重、24h 冷却全部沿用，不新建通道。

推送文案：标题「今天的萌照来了」，正文可带宠物名。

定时：后台循环每 10 分钟跑一次（复用健康扫描的节奏），判断「当前本地时间是否落在 `[start_hour, end_hour)` 且当天该 slot 还没发」，满足则生成并推送。

## 8. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/pets/{pet_id}/portraits?date=&limit=` | 成品列表（id/date/slot/crop_url/score/created_at） |
| GET | `/api/v1/pets/{pet_id}/portraits/today` | 当天最新一张（没有则 204） |
| POST | `/api/v1/portraits/{shot_id}/feedback` | body `{kind: "like"|"skip"|"crop_head", payload?: {...}}`；`skip` 返回同一天的下一张或 204 |
| GET/PUT | `/api/v1/pets/{pet_id}/portrait-settings` | 读/改 `enabled / per_day / start_hour / end_hour` |
| GET | `/api/v1/portraits/{shot_id}/image` | 成品图（带 `?token=`，与现有图片接口一致） |

全部走 Bearer 令牌，按 `owner_id` 隔离；非本人资源 404。

## 9. App 界面

1. **首页新增「今日萌照」卡片**（放在拍张照按钮下方）：显示当天成品缩略图 + 日期；没拍到则显示「今天它躲起来了」，不显示糊图。
2. **萌照详情页** `app/portrait/[id].tsx`：大图、日期、按钮「保存到相册」「分享」「换一张」「这张好看」。
3. **「我的 → 萌照相册」**：按天网格列表，点开小图进详情。
4. **「我的 → 萌照」设置**：开关、每天几张（1–3）、发送时段（起止小时）。

文案要求：不出现「置信度 / 得分 / 设备编号」；失败态说人话（「今天它躲起来了」「这张没生成好，明天再试」）。

## 10. 配置项（`SHEDGUARD_*`）

| 键 | 默认 | 说明 |
|---|---|---|
| `portrait_enabled` | `true` | 总开关，关闭则不扫描不投递 |
| `portrait_scan_minutes` | `10` | 投递检查间隔 |
| `portrait_min_subject_ratio` | `0.10` | 近景门槛 |
| `portrait_min_detector_confidence` | `0.45` | 检测门槛 |
| `portrait_max_output_px` | `640` | 成品长边 |
| `portrait_jpeg_quality` | `88` | 成品质量 |

配置 37 → 43 项。

## 11. 验收

1. 迁移 `0007 → 0008` 在已有数据库上自动升级成功。
2. 上传一张「守宫占画面 ≥10%」的图并触发选片，`portrait_shots` 生成 1 行，成品文件存在且为 1:1。
3. 守宫太小 / 全是反光 / 未检出时**不生成**，接口返回 204，App 显示「今天它躲起来了」。
4. `POST /feedback {kind:"skip"}` 返回同一天下一张（若还有候选），否则 204；`{kind:"like"}` 只记录。
5. 每人每天最多 `per_day` 张，重复调用不重复生成（唯一键）。
6. 关闭 `portrait_enabled` 后不扫描、不推送。
7. 别人的成品/反馈访问返回 404。
8. 单元测试覆盖打分函数（门槛/打分/去重各 2 条以上），集成测试覆盖上述 3–7。
9. `ruff` / `mypy src tests` / `pytest`（≥ 415 测试，覆盖率 ≥ 95%）全绿。

## 12. 已知限制

- V1 **不保证头部特写**；能否拍到脸取决于守宫是否凑近镜头。
- 夜间与红外不参与（沿用一期「白天才拍」）。
- 成品是二次编码的 JPEG，不能当证据图用；原图仍按原样保存在 `data/images/`。
- 每天 N 张的「槽位」是按固定时段均分，不等同于「随机抓拍 N 次」。
- 偏好数据目前只用于 V2 打分器，**不上传、不共享**，仅存在自己的服务器。
## 13. 实现记录（2026-11-13）

### 落地文件

| 层 | 文件 | 说明 |
|---|---|---|
| domain | `server/src/shedguard_server/domain/portrait.py` | 选片门槛、打分、正方形裁切、dHash、路径与编码（纯函数） |
| 表 | `server/src/shedguard_server/infra/tables.py` | `portrait_settings` / `portrait_shots` / `portrait_feedback` |
| 迁移 | `server/src/shedguard_server/migrations/versions/0008_portraits.py` | `0007 → 0008` |
| 仓储 | `server/src/shedguard_server/infra/repository.py` | 三个仓库 + `PushDeviceRepository.device_for_pet` |
| 服务 | `server/src/shedguard_server/services/portraits.py` | `PortraitService`（设置/生成/反馈）与 `scan_once` 后台扫描 |
| 接口 | `server/src/shedguard_server/api/routes/portraits.py` | 列表、今日、设置读写、反馈、成品图 |
| 配置 | `server/src/shedguard_server/config.py` | 6 项 `SHEDGUARD_PORTRAIT_*`（配置项 37 → 43） |
| App | `app/src/hooks/usePortraits.ts`、`app/src/app/portraits.tsx`、`app/src/app/portrait/[id].tsx`、`app/src/app/portrait-settings.tsx` | 首页「今天的萌照」卡、相册、详情、设置 |

### 实现偏差

| 偏差 | 原因 |
|---|---|
| 「换一张」只记录 `skip`，**不重新生成当天照片** | `portrait_shots` 的唯一键是 `(device_id, local_date, slot)`，当天槽位生成后不再覆盖；真正的「再来一张」要等 V2 的偏好打分器重排候选 |
| UI 只发 `like` / `skip`，**没有手动框头** | 拖拽框选需要手势与坐标换算，V1 先不做；接口与表已支持 `crop_head` + `crop_box`，等 P27 头部检测时再接 |
| `per_day > 1` 时**只有第一张会建提醒** | `alerts` 唯一键是 `(device_id, local_date, kind)`；第 2 张起只入库不推送 |
| 新增 `PortraitService.existing()` | 首版 `scan_once` 把「已存在、直接返回」当成新建，导致每小时扫描都会把计数 +1；改为先查后生成 |
| 图片 URL 用 `?token=` 且要等令牌就绪 | 与 `alert/[id]` 一致：`<Image>` 不能带请求头，未就绪时先显示占位 |

### 验收

- 服务端：**440 测试 / 0 失败 / 0 错误**，覆盖率 **95.15%**（门槛 85%）；`ruff check src tests` 全绿；`mypy src tests` 121 个文件无问题。
- App：`npx tsc --noEmit` 与 `npx eslint .` 全绿。
- 真机（Expo Web 430×932）截图核对：首页「今天的萌照」卡可见；相册显示缩略图与日期；详情页显示成品图与两个反馈按钮；设置页显示开关、每天张数、起止时间。
- 用真实模型跑通一次完整链路：上传真实蜕皮照片 → 检测/指标 → `scan_once` 生成 366×366 萌照（score 0.9968）。

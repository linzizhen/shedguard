# 摄像头接入层设计（P30）

> 状态：**草案，待批准**
> 日期：2026-11-16
> 前置：`docs/market-2026-11-16.md`（路线 C：成品摄像头 + 软件层）；`docs/plan.md` §2.1

## 1. 背景与目标

路线 C 定了「不自研硬件、不量产」，数据来源改成**用户已有的家用摄像头**。这一步要解决的是：怎么把一台别人家的摄像头，变成我们流水线的「图片来源」。

目标（一句话）：**用户添加一次摄像头，之后每 30 分钟自动抓一张，走现有的判定与提醒链路；用户不需要开电脑、不需要装网关。**

## 2. 范围

### 做

- 两种视频源适配器：**厂商云 API**（首个实现：萤石云）与**通用 RTSP/ONVIF**。
- 「摄像头」作为一种新的数据源实体：注册、测试连接、启停、删除。
- 定时抓拍调度：复用现有白天时段（`capture_start_hour` / `capture_end_hour`）与间隔。
- 抓到的帧走**现有上传流水线**（`IngestService` → 自动分析 → 状态判定 → 提醒），代码不复制。
- 失败兜底：连续抓拍失败达到阈值 → 生成 `camera_offline` 提醒（复用 P17 的提醒通道）。
- 凭据加密存储，接口永不回显。

### 不做

- 不自己做摄像头固件、不做 P2P 打洞、不做内网穿透服务。
- 不做实时视频流（只抓单帧）、不做录像回放。
- 不做多摄像头同箱视角融合（一台宠物一个摄像头，多对多先留接口）。
- 不优先支持「需要轮询云厂商计费接口」的品牌；每接一个品牌都要单独评估额度成本。

## 3. 总体架构

```
调度循环（每 camera_poll_minutes）
   └─ CameraRegistry（表 cameras）
        └─ CameraSource（适配器，按 provider 选择）
             ├─ EzvizSource   厂商云 API：取直播地址 → 解出 1 帧 JPEG
             └─ RtspSource    ONVIF 发现 + RTSP 拉流 → 解出 1 帧 JPEG
   └─ IngestService.ingest(JPEG, device_id=f"camera:{camera_id}", captured_at=now)
        └─ 现有：AnalysisService → SheddingService → 跃迁建 alert → 推送
```

要点：**适配器只负责「产出一张 JPEG」**，之后的落盘、去重、分析、判定、提醒全部复用既有代码。这样摄像头接入不会碰判定逻辑，也不会引入第二套数据模型。

## 4. 数据模型

新表 `cameras`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str (36) PK | |
| `owner_id` | str(36) FK users.id | 与宠物同级的隔离维度 |
| `pet_id` | str(36) FK pets.id，可空 | 该摄像头看哪只宠物；空表示未绑定 |
| `provider` | str(16) | `ezviz` / `rtsp` |
| `label` | str(64) | 用户起的名字，如「箱子里那个」 |
| `config_json` | text | **非敏感**配置：`{"device_serial": "...", "channel": 1, "rtsp_url": "rtsp://192.168.1.20:554/..."}`（**不含密码**） |
| `secret_enc` | text | **加密后**的敏感串：萤石 `app_key/app_secret/access_token`，或 RTSP 的 `user:password` |
| `enabled` | bool | 默认 true |
| `status` | str(24) | `ok` / `auth_failed` / `unreachable` / `never_tested` |
| `last_error` | str(200) 可空 | 最近一次失败的原因（人话，供 App 显示） |
| `last_frame_at_utc` | str(40) 可空 | |
| `consecutive_failures` | int | 连续失败次数，成功清零 |
| `created_at_utc` / `updated_at_utc` | str(40) | |

迁移：`0010_cameras.py`（`revision="0010"`，`down_revision="0009"`）。索引：`ix_cameras_owner_id`、`ix_cameras_pet_id`。

图片侧不加列：抓到的帧用 `device_id = f"camera:{camera_id}"` 进入 `images`，与 ESP32 设备完全同构（现有 `X-Device-Id` 校验要放行这种前缀）。

## 5. 适配器接口

```python
class CameraSource(Protocol):
    name: str
    def fetch_frame(self) -> bytes: ...       # 返回 JPEG 字节；失败抛 CameraError
```

```python
class CameraError(Exception):
    kind: str            # "auth_failed" | "unreachable" | "no_frame" | "bad_config"
    detail: str          # 人话，可直接给用户看
```

- `EzvizSource(config, secret)`：
  1. 用 `access_token` 调「获取直播地址」（`/api/lapp/live/address/get`，**具体路径与参数以开放平台文档为准，待申请到账号后核实**）；
  2. 从返回的 HLS/FLV 地址用 `ffmpeg` 或 `opencv` 解出**一帧**（不落视频流）；
  3. 失败按响应码分类成 `auth_failed`（token 过期）或 `unreachable`。
- `RtspSource(config, secret)`：
  1. `cv2.VideoCapture(rtsp_url)`，设 `CAP_PROP_OPEN_TIMEOUT_MSEC` / `CAP_PROP_READ_TIMEOUT_MSEC`；
  2. `read()` 一次，`imencode(".jpg")` 返回；
  3. 打不开 → `unreachable`；打开但读不出 → `no_frame`。
- 两个实现都**不重试**（重试由调度层按 30 分钟周期自然发生），避免卡死后台线程。

## 6. 抓拍调度

- 复用 `app.py` 的 lifespan 后台任务范式（同 `_portrait_loop`、`_contribution_loop`）。
- 每 `camera_poll_minutes`（默认 30）一轮：遍历 `enabled` 且已绑定宠物的摄像头；只在 `capture_start_hour..capture_end_hour` 内抓（默认 08:00–20:00，与固件一致）。
- 单轮每台摄像头最多抓 1 帧；抓取失败 → `consecutive_failures += 1`、`status` 按 `kind` 落库；成功 → 清零、`last_frame_at_utc` 更新。
- `consecutive_failures >= camera_max_failures`（默认 3）→ 建提醒 `camera_offline`（kind 新增，唯一键 `(camera_id, local_date, kind)`）；恢复后不再重复提醒。
- 抓拍串行执行（用户量小时足够）；超过 50 台再引入并发池。

## 7. 配对与凭据

- **凭据加密**：`SHEDGUARD_SECRET_KEY`（Fernet key，base64 32 字节）。未配置时**拒绝保存带密码的凭据**并给出人话错误，而不是明文落库。启动时校验格式。
- 新依赖：`cryptography>=42`（放入 `pyproject.toml`）。
- 接口永远不回显 `secret_enc`；`config_json` 只回显非敏感字段。
- 萤石流程：用户在萤石 App 里把摄像头加到自己账号 → 我们在开放平台申请「应用」拿 `app_key/app_secret` → 用户在网页端授权后我们拿到其设备序列号 → 服务端换 `access_token`。**这一步必须写清「个人开发者申请企业应用需要资质」，见 §12。**
- RTSP 流程：用户填 `rtsp://<用户名>:<密码>@<ip>:554/<路径>`，服务端把用户名密码拆出来单独加密，`config_json` 里只留去掉凭据的地址。

## 8. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/cameras` | 注册摄像头（`provider`、`label`、`pet_id`、`config`、`secret`）→ 201 |
| `GET` | `/api/v1/cameras` | 我的摄像头列表（含 `status`、`last_frame_at_utc`、`last_error`） |
| `PATCH` | `/api/v1/cameras/{id}` | 改名 / 换宠物 / 启停 / 换凭据 |
| `DELETE` | `/api/v1/cameras/{id}` | 删除（保留已抓到的历史图片） |
| `POST` | `/api/v1/cameras/{id}/test` | 立即抓一帧验证连通性，**不落库**，返回 `{ok, kind, detail, took_ms}` |
| `POST` | `/api/v1/cameras/{id}/snapshot` | 立即抓一帧并**入库走完流水线**（用于现场调试与首次体验） |

权限：全部要求登录态（`get_current_user`），非本人资源 404。

## 9. App 改动

- 「我的」新增「摄像头」入口 → `app/cameras.tsx`（列表：名字 / 状态灯 / 最近一张 / 上次抓拍时间）+ `app/camera/new.tsx`（选择类型：萤石云 / 通用 RTSP → 填字段 → 「测一下」）。
- 添加流程文案必须人话：「先确认摄像头和你手机在同一个网里」「密码只存在你自己的服务器上，我们不会显示」。
- 状态灯四态：`ok`（绿）/ `auth_failed`（橙，提示「授权过期了，重新登录一次」）/ `unreachable`（红，提示「连不上，检查 wifi 或地址」）/ `never_tested`（灰）。
- 首页在没有任何图片来源时，提示「先添加一个摄像头，或者直接用手机拍」——保留手机拍照兜底。

## 10. 配置项（52 → 57）

| 配置 | 默认 | 说明 |
|---|---|---|
| `SHEDGUARD_CAMERA_ENABLED` | `true` | 关闭后不启动抓拍循环 |
| `SHEDGUARD_CAMERA_POLL_MINUTES` | `30` | 抓拍间隔（1–720） |
| `SHEDGUARD_CAMERA_TIMEOUT_SECONDS` | `15` | 单次取帧超时（3–120） |
| `SHEDGUARD_CAMERA_MAX_FAILURES` | `3` | 连续失败多少次发 `camera_offline` |
| `SHEDGUARD_SECRET_KEY` | `""` | Fernet key，空表示不接受带密码的凭据 |

## 11. 测试与验收

- 单元：`EzvizSource` / `RtspSource` 用假客户端（不碰网络）；错误码到 `CameraError.kind` 的映射；凭据加解密往返；未配置 `SECRET_KEY` 时拒收密码。
- 集成：注册摄像头 → `snapshot` → `images` 多一行且 `device_id="camera:<id>"` → 流水线产出 `shedding_states`；连续 3 次失败 → 1 条 `camera_offline`，第 4 次失败不重复建；`test` 端点不落库；凭据不出现在任何响应里。
- 验收（必须有一条「真东西」）：**用一个真实摄像头（RTSP 或萤石云任一）跑通 `snapshot`，并把这一帧送进现有判定链路看到结果**。
- 质量门同前：`ruff check .`、`mypy src tests`、`pytest --junitxml`（基线 480 测试 / 94.06%）。

## 12. 风险与已知限制

1. **萤石开放平台需要企业资质与应用审核**（个人开发者大概率过不了）——这是本方案最大的外部依赖。缓解：RTSP 路径先跑通，厂商云 API 并行申请；若拿不到资质，退回「用户端网关 + 云服务」（路线 B）。
2. **厂商 API 有调用配额与计费**：每 30 分钟抓一帧、一台一天 24 次，20 台用户约 480 次/天，需在申请时确认额度。
3. **RTSP 要求服务端能路由到摄像头**：托管部署下做不到，只有自托管（用户家里跑服务端）或未来的用户端网关才行——这也是为什么需要同时保留 RTSP 实现。
4. **画面与训练集不同分布**：广角鱼眼、夜视红外、玻璃反光、俯视角度都是新分布，P22 的组合退化召回只有 0.6374，真实表现待 P31 验证。
5. **凭据安全**：`SECRET_KEY` 泄露等于用户摄像头密码泄露；文档要求单机生成、不进仓库、可轮换。
6. **多品牌成本**：每接一个厂商都要读文档 + 申请 + 适配 + 维护，第二个品牌之前应先用 P31 验证需求是否成立。

## 13. 实现记录（2026-11-16）

### 13.1 落地文件

| 层 | 文件 | 内容 |
|---|---|---|
| 领域 | `server/src/shedguard_server/domain/camera.py` | 适配器契约、错误分类、配置拆分与脱敏、设备编号映射 |
| 持久化 | `server/src/shedguard_server/infra/tables.py` | `CameraRow` |
| 迁移 | `server/src/shedguard_server/migrations/versions/0010_cameras.py` | `0010`，`cameras` 表 + 两个索引 |
| 持久化 | `server/src/shedguard_server/infra/repository.py` | `CameraRepository`（get / list_for_owner / list_enabled / add / save / delete） |
| 基础设施 | `server/src/shedguard_server/infra/crypto.py` | Fernet 封装；没配密钥时用 `NullSecretBox` 拒绝保存密码 |
| 基础设施 | `server/src/shedguard_server/infra/camera_sources.py` | `RtspSource`、`EzvizSource`、`build_camera_source`、带硬超时的抓帧 |
| 服务 | `server/src/shedguard_server/services/cameras.py` | 增删改查、`test`、`snapshot`、`poll_once` 调度与离线提醒 |
| 接口 | `server/src/shedguard_server/api/routes/cameras.py` | 6 个端点，配置脱敏后返回 |
| 装配 | `server/src/shedguard_server/app.py`、`config.py`、`dependencies.py` | `_camera_loop`、5 项配置、仓库依赖 |
| 测试 | `tests/unit/test_camera_domain.py`、`tests/unit/test_camera_sources.py`、`tests/integration/test_cameras_api.py` | 40 条（39 + 1 条抓帧超时） |

### 13.2 实现偏差

| 规格 | 实际做法 | 原因 |
|---|---|---|
| `device_id = "camera:<id>"` | 改成 `camera-<id>`（短横线） | `validate_device_id` 只允许 `[A-Za-z0-9_-]`，冒号会被拒 |
| 抓帧超时靠 OpenCV 的 open/read 超时属性 | 抓帧放线程池，`future.result(timeout=...)` 硬切 | 实测 `CAP_PROP_OPEN_TIMEOUT_MSEC` 在 FFMPEG 后端不生效，连不通的地址能挂 30 秒以上，会把后台循环和请求一起拖住 |
| `test` 返回 200 + 结果对象 | 保持 | 与「测试连接不算业务失败」一致；真正的失败仍走 `snapshot` 的 502 |
| 规格写 6 个接口 | 保持 6 个 | 无变动 |
| 只给 `has_secret`，不返回密文 | 保持，且 `config` 里连 RTSP 账号也只回 `rtsp://u:***@host/path` | 防日志与截图泄露 |

### 13.3 验收对照

| 验收项 | 结果 |
|---|---|
| 未配置 `SECRET_KEY` 时保存密码被拒 | ✅ 400，文案「服务器还没配置密钥，暂时不能保存摄像头密码」 |
| 配置里不出现密码、响应里不出现密文 | ✅ 单测 + 集成测试均断言 |
| `test` 不落库 | ✅ 只更新状态与失败计数 |
| `snapshot` 走同一条流水线 | ✅ 202 + `images` 多一行，`device_id=camera-<id>` |
| 连续失败到阈值建 1 条 `camera_offline` | ✅ 第 3 次建，第 4 次不重复 |
| 关闭 `SHEDGUARD_CAMERA_ENABLED` 不启动循环 | ✅ `app.state.camera_task` 不存在 |
| 抓帧整体有硬超时 | ✅ 15 秒返回 `unreachable`，单元测试用 0.05 秒切断验证 |
| 质量门 | ✅ 520 测试 / 0 失败；覆盖率 93.14%；`ruff check .` 与 `mypy src tests`（138 文件）全绿 |

### 13.4 冒烟结果（本地 8004，RTSP 指向不可达地址）

- `POST /api/v1/cameras` → 201，`config` 只剩 `{"url": "rtsp://10.255.255.1:554/stream1"}`，`has_secret=true`，`status=never_tested`。
- `POST /cameras/{id}/test` → 200，`{"ok": false, "kind": "unreachable", "detail": "连摄像头超时了，检查地址、电源和网络", "took_ms": 15012}`。
- `POST /cameras/{id}/snapshot` → 502 `CAMERA_UNAVAILABLE`，与 test 同一句人话。
- `GET /api/v1/cameras` → `status=unreachable`，`consecutive_failures=2`（test + snapshot 两次失败）。

### 13.5 还没验证的

- **没有任何真实摄像头**参与过：RTSP 用的是不可达地址（验证的是失败路径），萤石云的接口路径按公开文档写、账号未开通。
- 萤石开放平台的应用审核（企业资质）尚未申请。
- 抓帧在真实局域网下的耗时、夜间画面、玻璃反光下的成片质量都未观察。

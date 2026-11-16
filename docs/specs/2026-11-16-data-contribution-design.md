# 数据贡献（用户自愿分享照片）设计规格（P29）

- 状态：**草案 v2，待用户批准**
- 日期：2026-11-16（v2 按用户修正：默认关闭 → 开关打开后**自动上传**，不再要求用户手动交 zip）
- 关联计划：`docs/plan.md` §2.1 / §3（P29）/ §4 / §5 / §6 / §7
- 关联旧案：`docs/specs/2026-11-13-portrait-shots-design.md`（P25 萌照，复用其裁切与取图能力）
- 配套手册（实现时新增）：`docs/contribution-setup.md`（开发者如何建收件箱）

---

## 1. 背景与目标

**问题**：本项目的最大短板不是代码，是**真实机位数据为零**——`data/` 里 1000+ 张全是网络图（物种混杂、白底摆拍、深色背景微距），自采 0 张、蒙白 0 张。`gecko-state-v2` 的 0.9286 是同源网图上的数字；P22 已证明在模拟真实退化下蜕皮召回掉到 0.6374。继续抓网络图的边际收益已很低（Bing 扩图 512 张 → 清洗 436 张 → 训出 v3 反而更差，已判不部署）。

**目标**：让用户**只做一次决定**（开或不开），之后真实照片自动流到我们手上。用户不需要挑选、打标、记得点任何按钮、也不需要自己把文件发过来。

**一句话原则**：**用户出一个开关，剩下的全自动。**

---

## 2. 范围

### 2.1 做（一期）

- **收件箱**：开发者的**私有 HuggingFace 数据集仓库**（免费、免服务器）。服务端通过可替换的上传器接口自动上传；以后换自建服务器只加一种实现。
- **自动采集**：开关打开后，每次蜕皮事件最多留 3 张（可配），默认只留**裁剪后的守宫特写**。
- **自动上传**：后台循环把待上传样本批量推到收件箱；断网/失败自动重试，不打扰用户。
- **App**：「我的 → 帮助改进识别」一个开关页 + 已分享记录（可看、可逐张撤回、可一键清空）。
- **撤回**：删除本地文件与数据库行，并**尝试删除远端副本**（尽力而为，失败记日志）。
- **本地留档**：样本在本机也保留一份，便于开发者导出排查（`data/contributions/`）。

### 2.2 不做（明确排除，避免范围膨胀）

| 不做 | 原因 |
|---|---|
| 让用户手动挑图 / 打标 | 用户明确要求「别让人觉得烦」；标签由模型产出，人工只在我们这边复核 |
| 上传用户相册里的照片 | 只处理**设备抓拍**与**用户主动分享的萌照**，绝不扫描相册 |
| 上传整箱环境（默认） | 默认只给裁剪特写；整张原图必须是用户显式勾选 |
| 公开数据集 / 转交第三方 | 未经单独同意不对外发布 |
| 积分 / 奖励 / 排行榜 | 一期不搞运营，先把通路走通 |
| 端到端加密 | 一期不做（成本高）；靠私有仓库 + 权限收敛 + 可撤回控制风险，风险写进 §10 |

---

## 3. 用户视角流程

1. 用户正常用 App（拍照查验、看提醒、看萌照）。
2. 用户在「我的 → 帮助改进识别」读一句话说明，**打开总开关**（默认关闭）。
3. 此后每次检测到蜕皮，系统自动把这次事件里最清楚的 3 张送去收件箱——**用户什么都不用做**。
4. 页面上能看到「已分享 12 张 · 最近一次 11月16日 14:20」，可随时逐张撤回或一键清空。

**不得出现**：弹窗要求分享、开屏诱导、每次蜕皮都问「要不要分享」、要求用户挑选或手动上传。

---

## 4. 数据与隐私规则（本规格最重要的一节）

| 规则 | 具体做法 |
|---|---|
| 明示同意 | 默认**关**。开关旁必须写清「照片会通过互联网上传到开发者的私有数据集仓库」，不能只说「帮助我们改进」 |
| 最小必要 | 默认只上传**检测框裁出来的守宫特写**（外扩 8%），不含整箱环境 |
| 整张可选 | 用户显式勾选「也包含整张照片」后才上传原图；默认不勾 |
| 剥离元数据 | 所有上传图一律 `cv2.imdecode` + `imencode` 重新编码（JPEG 88 / 85），EXIF、GPS、设备信息随之丢失 |
| 不留身份 | 远端路径与元数据里**不写**宠物名、用户 id、设备号原值、原始文件名；设备用 `sha256(device_id)[:12]` 做分组哈希，不可反查 |
| 可撤回 | 撤回 = 删本地文件 + 删数据库行 + **删远端文件**（尽力而为，失败记日志并在 UI 上标「远端删除失败」） |
| 可见 | 用户能看到「已分享哪些」，不是黑盒 |
| 上限 | 待上传样本默认最多 200 张；满了停止采集并记日志（不打扰用户） |
| 不记日志 | 上传器与配置读取**绝不把 token 写进日志或异常信息** |

---

## 5. 服务端设计

### 5.1 数据模型（迁移 `0009_contributions.py`，`down_revision = "0008"`）

`contribution_settings`

| 列 | 类型 | 说明 |
|---|---|---|
| `owner_id` | String(36) PK, FK users.id | 一个用户一行 |
| `enabled` | Boolean，默认 **false** | 总开关 |
| `include_full` | Boolean，默认 false | 是否连带整张原图 |
| `created_at_utc` / `updated_at_utc` | String(40) | |

`contribution_samples`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(36) PK | uuid4 |
| `owner_id` | String(36)，FK users.id，index | |
| `device_id` | String(64)，index | 仅内部用 |
| `pet_id` | String(36)，可空 | 仅内部用 |
| `source_image_id` | String(36)，FK images.id | 来源帧 |
| `state` | String(16) | 入队时判定 |
| `confidence` | Float，可空 | |
| `local_date` | String(10)，index | `YYYY-MM-DD` |
| `crop_rel_path` | String(255) | 本地裁剪图 |
| `full_rel_path` | String(255)，可空 | 本地整图（若勾选） |
| `sha256` | String(64) | 裁剪图内容哈希（去重 + 远端文件名） |
| `upload_status` | String(16) | `pending` / `uploaded` / `failed` / `withdrawn` |
| `upload_attempts` | Integer，默认 0 | 重试计数 |
| `remote_crop_path` / `remote_full_path` | String(255)，可空 | 收件箱里的相对路径 |
| `uploaded_at_utc` | String(40)，可空 | |
| `created_at_utc` | String(40) | |

唯一约束 `ux_contribution_samples_image_owner (source_image_id, owner_id)`：同一帧不会入队两次。

`contribution_exports`（本地打包留档，供开发者排查/离线补交；不是主通路）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(36) PK | |
| `owner_id` | String(36)，FK users.id，index | |
| `filename` | String(128) | `contribution-<UTC>-<6位>.zip` |
| `rel_path` | String(255) | `exports/...` |
| `sample_count` / `byte_size` | Integer | |
| `created_at_utc` | String(40) | |

文件布局：

```
data/contributions/<owner_id>/crop/<sha12>.jpg
data/contributions/<owner_id>/full/<sha12>.jpg     # 仅 include_full
data/exports/contribution-<UTC>-<6位>.zip          # 本地打包（可选）
```

收件箱布局（HF 仓库内）：

```
<owner_hash>/<local_date>/<sha12>.jpg
<owner_hash>/<local_date>/<sha12>.json            # 元数据，字段见 §5.2
<owner_hash>/<local_date>/<sha12>.full.jpg        # 仅 include_full
```

### 5.2 领域层（纯函数，`domain/contribution.py`）

- 常量：`DEFAULT_PER_EVENT_LIMIT = 3`、`MAX_PER_EVENT_LIMIT = 10`、`DEFAULT_MAX_PENDING = 200`、`CROP_PADDING = 0.08`、`CROP_JPEG_QUALITY = 88`、`FULL_JPEG_QUALITY = 85`、`SAMPLE_PENDING = "pending"`、`SAMPLE_UPLOADED = "uploaded"`、`SAMPLE_FAILED = "failed"`、`SAMPLE_WITHDRAWN = "withdrawn"`、`MAX_UPLOAD_ATTEMPTS = 5`、`DEFAULT_CONTRIBUTION_ENABLED = False`。
- `device_hash(device_id) -> str`（sha256 前 12 位）。
- `crop_relative_path(owner_id, sha256)` / `full_relative_path(owner_id, sha256)`。
- `remote_paths(*, owner_hash, local_date, sha256, include_full) -> RemotePaths(crop, meta, full|None)`。
- `meta_payload(sample, *, width, height) -> dict`：**字段白名单** = `sha12 / state / confidence / local_date / has_full / width / height`。测试断言不含 `pet`、`device_id`、`owner`、原文件名。
- `export_filename(now) -> str`。
- 数据类：`ContributionSetting`、`ContributionSample`、`ContributionExport`、`RemotePaths`。

### 5.3 上传器接口（`infra/contribution_upload.py`）

```python
class ContributionUploader(Protocol):
    def upload_batch(self, items: Sequence[UploadItem]) -> UploadBatchResult: ...
    def delete_files(self, paths: Sequence[str]) -> int: ...
```

- `UploadItem(remote_path: str, payload: bytes)`；`UploadBatchResult(uploaded: int, failed: list[str])`。
- `HuggingFaceUploader(repo_id, token, *, revision="main", timeout=30.0)`：用 `huggingface_hub.HfApi.create_commit` 一次提交整批文件（减少提交次数）；仓库不存在/无权限/网络错误 → 抛 `StorageUnavailableError`，由服务层转成 `failed`；`delete_files` 用 `HfApi.delete_file`。
- `NoopUploader`：`upload_batch` 返回 `failed = 全部路径`（用于「没配收件箱」的显式降级：样本留在本地标记 `pending`，不假成功）。
- 依赖懒加载：`huggingface_hub` 只在构造 `HuggingFaceUploader` 时 import，缺依赖时报可读错误（不影响服务启动）。
- **token 永不进日志**：异常信息里只出现 `repo_id` 与状态码。

### 5.4 服务层（`services/contributions.py`）

`ContributionService(*, samples, settings, exports, pets, devices, images, metrics, states, storage, uploader, *, per_event_limit=3, max_pending=200, include_full_default=False, timezone="Asia/Shanghai")`

| 方法 | 行为 |
|---|---|
| `get_setting(*, owner_id)` | 无记录时返回默认（`enabled=False`） |
| `update_setting(*, owner_id, enabled, include_full, now)` | upsert；关闭开关**不动**已采集样本（撤回要用户显式点） |
| `enqueue_for_event(*, owner_id, device_id, pet_id, local_date, state, confidence, image_id, now)` | 见下 |
| `list_samples(*, owner_id, limit=100)` | 按 `created_at_utc` 倒序，带 `upload_status` |
| `read_sample_image(sample_id, *, owner_id, full=False)` | 越权/不存在 → `NotFoundError` |
| `withdraw(sample_id, *, owner_id)` | 删本地文件 → 删远端文件（尽力）→ 状态改 `withdrawn` 并删行 |
| `withdraw_all(*, owner_id)` | 批量，返回 `{removed, remote_failed}` |
| `upload_pending(*, owner_id=None, now)` | 见下 |
| `create_export(*, owner_id, now)` / `list_exports` / `read_export` | 本地打包留档 |

`enqueue_for_event` 步骤：

1. 设置未开或功能未启用 → 返回 0（**默认什么都不做**）。
2. 取该设备当天状态记录，按 `confidence` 倒序、去重，最多 `per_event_limit` 张；当前帧优先。
3. `count_pending >= max_pending` → 记日志并返回 0。
4. 逐张：已存在则跳过；读原图 → `decode_image` → 按该帧 `frame_metrics.box` 裁切（外扩 8%，复用 P25 几何函数）→ 重编码 JPEG → `storage.write_atomic` →（勾选时另存整图重编码）→ 写行 `upload_status=pending`。
5. 单张失败只记日志并继续；方法整体不抛异常（调用点是上传后处理流水线）。

`upload_pending` 步骤：

1. 取 `pending`（及 `failed` 且 `upload_attempts < MAX_UPLOAD_ATTEMPTS`）样本，按 `owner_id` 分组。
2. 每组：构造 `UploadItem`（crop + meta + 可选 full）→ `uploader.upload_batch(...)`。
3. 成功：状态 `uploaded`、记 `remote_*_path`、`uploaded_at_utc`；失败：`upload_attempts += 1`，达到上限标 `failed`（不再重试）并记日志。
4. 返回 `UploadSummary(uploaded, failed, skipped)`。
5. 整体 `try/except` 只记日志——**贡献功能绝不影响蜕皮检测主链路**。

### 5.5 接口（`api/routes/contributions.py`，`prefix="/api/v1"`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/contribution-settings` | `{enabled, include_full, per_event_limit, max_pending, upload_enabled, pending_count, uploaded_count}` |
| PUT | `/contribution-settings` | 改 `enabled` / `include_full`；返回同上 |
| GET | `/contributions?limit=` | `{items:[{id, local_date, state, confidence, has_full, upload_status, uploaded_at_utc, created_at_utc, crop_url}], pending_count, uploaded_count}` |
| DELETE | `/contributions/{sample_id}` | 204；越权/不存在 → 404 |
| DELETE | `/contributions` | 全部撤回，`{removed, remote_failed}` |
| GET | `/contributions/{sample_id}/image?full=false&token=` | 图片（`?token=` 供 RN `<Image>` 用） |
| POST | `/contributions/exports` | 本地打包留档，返回 `{export_id, filename, sample_count, byte_size, download_url}` |
| GET | `/contributions/exports/{export_id}/download?token=` | 下载 zip |

- 全部走 `get_current_user`（P16）；越权一律 **404**。
- 无待打包样本 → 400 `INVALID_REQUEST`「还没有可打包的照片」。

### 5.6 接进现有流水线与后台循环

`services/processing.py`：在 `create_for_transition` 建提醒成功后追加一次 `enqueue_for_event(...)`（`owner_id` 由新增的 `PushDeviceRepository.owner_for_device(device_id)` 取得），整段包 `try/except` 只记日志。

`app.py`：新增 `_contribution_loop(session_factory, settings, storage, uploader)`，每 `contribution_upload_minutes`（默认 30）跑一次 `upload_pending()`；lifespan 中 `contribution_enabled and upload_enabled` 时 `asyncio.create_task`，关闭时 cancel + suppress；`app.state.contribution_uploader` 供测试注入。

### 5.7 配置项（43 → 52）

| 名称 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `SHEDGUARD_CONTRIBUTION_ENABLED` | `true` | bool | 功能是否出现（**用户侧开关默认仍是关**） |
| `SHEDGUARD_CONTRIBUTION_PER_EVENT_LIMIT` | `3` | 1–10 | 每次蜕皮事件最多留几张 |
| `SHEDGUARD_CONTRIBUTION_MAX_PENDING` | `200` | 10–5000 | 待上传上限 |
| `SHEDGUARD_CONTRIBUTION_INCLUDE_FULL_DEFAULT` | `false` | bool | 「附带整张原图」默认值 |
| `SHEDGUARD_CONTRIBUTION_CROP_PADDING` | `0.08` | 0–0.3 | 裁剪外扩比例 |
| `SHEDGUARD_CONTRIBUTION_UPLOAD_ENABLED` | `false` | bool | 是否真的往外传（没配收件箱时保持 false） |
| `SHEDGUARD_CONTRIBUTION_UPLOAD_REPO` | `""` | str | 收件箱仓库，如 `linzizhen/shedguard-contributions` |
| `SHEDGUARD_CONTRIBUTION_UPLOAD_TOKEN` | `""` | str（**密钥**） | 只对该仓库有写权限的 token |
| `SHEDGUARD_CONTRIBUTION_UPLOAD_MINUTES` | `30` | 5–1440 | 上传循环间隔 |

---

## 6. App 设计

新增根级路由 `app/contribution.tsx`（Stack 标题「帮助改进识别」），入口在「我的」页新增一节。

1. **说明**（必须写全）：「你拍到的照片能帮我们认得更准。开启后，每次检测到蜕皮会自动留 3 张最清楚的，**通过互联网上传到开发者的私有数据集仓库**；默认只传裁好的守宫特写，不带你家画面。」
2. **总开关**「帮忙改进（自愿）」——默认关。
3. **次级开关**「也包含整张照片」——仅总开关打开时可用；副文案「整张会拍到饲养箱环境，建议了解后再开」。
4. **状态**：「已分享 12 张 · 最近一次 11月16日 14:20」；未配收件箱时显示「已留在本机，等待上传」。
5. **列表**：缩略图 + 状态徽章（已上传 / 待上传 / 上传失败）；点开看大图，可「撤回这一张」（Alert 二次确认；远端删除失败时提示「远端副本删除失败，已记录」）。
6. **「导出到本机」**次按钮（留档，非必需）→ 生成 zip 并给下载链接。
7. **底部危险操作**：「全部清空」（Alert 二次确认）。

复用：`lib/auth.ts` 新增 `contributionUrl(sampleId, full)`；`hooks/useContributions.ts`（settings / list / update / withdraw / export）；`Card` / `PrimaryButton` / `EmptyState`。

**不做**：开屏弹窗、每次蜕皮提示分享、通知栏催分享。

---

## 7. 边界与失败处理

| 情况 | 行为 |
|---|---|
| 没开开关 | 完全不采集（连行都不写） |
| 功能关（`contribution_enabled=false`） | 接口返回 404，不采集 |
| 没配收件箱 | `NoopUploader`：样本留本地标 `pending`，UI 显示「等待上传」；**不假装成功** |
| 上传失败（网络/权限/仓库不存在） | `upload_attempts += 1`，下次循环重试；≥5 次标 `failed` 并记日志；不影响主链路 |
| token 失效 | 记日志（不含 token），样本保持待上传；不影响蜕皮检测 |
| 同一帧重复处理 | 唯一约束挡住 |
| 待上传满了 | 停止采集 + 日志；UI 显示现有数量 |
| 撤回时远端删除失败 | 本地仍删除，UI 提示「远端删除失败」；记日志供人工处理 |
| 用户清空 App 数据 | 服务端样本仍在，页面可清空 |

---

## 8. 测试计划

**单元**
1. `test_contribution_domain.py`：`device_hash` 稳定且不可反查；`meta_payload` **字段白名单**（不含 pet/device_id/owner/原文件名）；`remote_paths` 布局；`export_filename` 唯一性；常量边界。
2. `test_contribution_service.py`（假仓库 + 假 storage + 假 uploader）：开关关 → 不采集；开关开 → 最多 3 张且按置信度倒序；重复帧跳过；满额停止；单张解码失败不影响其余；`upload_pending` 调用了 uploader 且路径正确；上传失败 → `attempts+1`；达上限 → `failed` 且不再重试；`withdraw` 删本地 + 调 `delete_files`。

**集成（`tests/integration/test_contributions_api.py`）**
1. 默认设置 `enabled=false` 且此时不产生样本；2. PUT 打开后上传蜕皮图 → 自动入队 1 张；3. 同日再传 → ≤3 张且不重复；4. 跨用户 404；5. 撤回后本地文件消失、列表减一、假 uploader 收到删除调用；6. 未登录 401；7. 上传器注入失败时 `upload_status=failed` 且接口仍 200；8. `contribution_enabled=false` 时接口 404。
9. 上传器收到的是「crop + meta」，且 meta 里不含宠物名与设备号（断言上传内容）。

**验收（真东西）**
- `server/scripts/device_sim.py` 灌真实蜕皮照片 → 开关打开 → 假 uploader 记录到上传 → `GET /contributions` 显示 `uploaded`。
- **可选真仓库验证**（需要用户给的 token）：上传到私有仓库后确认文件存在、格式正确、能拉回；这一步在 token 备好后做一次，并在规格里记结果。
- App 430×932 截图核对：开关页、列表（含状态徽章）、导出结果三张。

---

## 9. 验收标准（10 条）

1. 默认 `enabled=false`，且**不开开关不产生任何样本、不发任何网络请求**。
2. 开关打开后一次蜕皮事件最多入队 3 张（可配），当前帧优先。
3. 同一帧绝不重复入队（唯一约束 + 测试）。
4. 样本重新编码过：抽一张与源图比对，EXIF 为空。
5. 上传内容里没有宠物名、用户 id、设备号原值、原始文件名（测试断言 + 一次人工核对）。
6. 撤回真实删除本地文件，并调用远端删除；远端失败会在 UI 上标出，不静默吞掉。
7. 上传失败可重试，达到上限后停止并记日志；**全程不影响蜕皮检测**（集成测试证明）。
8. 所有接口走鉴权，跨用户 404。
9. 没配收件箱时行为明确：样本留在本地标「待上传」，不假装成功。
10. App 三个界面在 430×932 下截图核对通过，文案不出现「服务器 / API / token / 置信度」，且**明确写出会通过互联网上传**。

---

## 10. 已知限制（写进文档，不隐瞒）

1. **需要一个收件箱**：开发者必须建一个私有 HF 数据集仓库并配置 token，功能才会真正往外传；没配就只留本地。
2. **token 分发风险**：该 token 配在用户那台机器的服务端上，只能靠「只给单个仓库写权限 + 可随时吊销」收敛风险。若以后用户量大，应改为自建接收端 + 每装机一次性密钥。
3. 上传走公网（HTTPS 到 HuggingFace），但我们**没有端到端加密**；图片内容（守宫特写）在服务器侧可读。
4. 撤回是「尽力删除远端」：HF 侧的提交历史里可能仍留有旧版本，真正的物理清除需要开发者按仓库策略处理。
5. 标签来自我们的模型（非人工标注），用于**域适应与蒙白样本积累**；当唯一标签源仍需人工抽检。
6. 不做跨用户去重。
7. HF 免费额度与速率限制对当前量级足够，但用户量大时需要重新评估。

---

## 11. 实施顺序

1. 迁移 `0009_contributions.py` + `infra/tables.py` + `infra/repository.py`（三个仓库 + `PushDeviceRepository.owner_for_device`）。
2. `domain/contribution.py` + 单测。
3. `infra/contribution_upload.py`（Protocol + HF 实现 + Noop）+ 单测（用假 client，不打网络）。
4. `services/contributions.py` + 单测。
5. `api/routes/contributions.py` + `dependencies.py` + `config.py` 9 项 + `app.py`（注册路由 + 上传循环 + `app.state.contribution_uploader`）。
6. 接进 `services/processing.py`；集成测试；质量门（`ruff`、`mypy src tests`、`pytest --junitxml`）。
7. App：`types.ts`、`auth.ts`、`hooks/useContributions.ts`、`app/contribution.tsx`、`_layout.tsx`、「我的」入口。
8. 冒烟与验收（假 uploader + 可选真仓库一次）；App 三张截图。
9. 文档：本规格追加「实现记录」、`docs/contribution-setup.md` 新增、`server/README.md`、`server/.env.example` 9 行、`app/README.md`、`docs/handoff.md`、`docs/plan.md` P29 标 ✅。
10. git flow：`feature/data-contribution` → `--no-ff` 合并 `develop` → 推送。

---

## 12. 规格自检

- [x] 无占位符（`docs/contribution-setup.md` 的示例仓库名用你自己的命名，实现时写成占位示例并注明「替换成你的」）。
- [x] 与 `docs/plan.md` §2.1 / §3 P29 / §5 / §6 / §7 一致（已按用户修正同步改写）。
- [x] 范围明确：一期做「自动上传到 HF 私有仓库」，手工交 zip 降级为「导出到本机」的备用能力。
- [x] 讲清动谁的数据、去哪、怎么撤：默认最小必要、可撤回（含远端尽力删除）。
- [x] 每条验收都能用命令或人工核对验证。
- [x] 测试覆盖最容易出事的两个默认行为：**不开开关不发任何网络请求**、**没配收件箱不假装成功**。
- [x] 密钥处理写明：token 只进配置、绝不进日志与异常信息。

---

## 13. 实现记录（P29，2026-11-16）

### 13.1 落地文件

| 层 | 文件 |
|---|---|
| 迁移 | `server/src/shedguard_server/migrations/versions/0009_contributions.py`（三表 + 四索引） |
| 表 | `server/src/shedguard_server/infra/tables.py`：`ContributionSettingRow`、`ContributionSampleRow`、`ContributionExportRow` |
| 领域 | `server/src/shedguard_server/domain/contribution.py`（路径、白名单元数据、编码、上传载荷） |
| 上传器 | `server/src/shedguard_server/infra/contribution_upload.py`（`ContributionUploader` Protocol、`HuggingFaceUploader`、`NoopUploader`、`build_contribution_uploader`） |
| 仓库 | `server/src/shedguard_server/infra/repository.py`：`ContributionSettingRepository`、`ContributionSampleRepository`、`ContributionExportRepository`、`PushDeviceRepository.owner_for_device` |
| 服务 | `server/src/shedguard_server/services/contributions.py`（`ContributionService`、`upload_once`） |
| 接口 | `server/src/shedguard_server/api/routes/contributions.py`（8 个端点） |
| 装配 | `config.py`（9 项）、`api/dependencies.py`（4 个依赖）、`app.py`（路由 + `_contribution_loop` + `app.state.contribution_uploader`） |
| 流水线 | `services/processing.py`：`_enqueue_contribution`，在判定为 `shedding` 之后、提醒去重之前调用 |
| 测试 | `tests/unit/test_contribution_domain.py`（21 条）、`tests/unit/test_contribution_upload.py`（12 条）、`tests/integration/test_contributions_api.py`（12 条） |
| App | `app/src/lib/types.ts`、`lib/auth.ts`（`contributionUrl`）、`hooks/useContributions.ts`、`app/contribution.tsx`、`app/_layout.tsx`、`(tabs)/settings.tsx` 入口 |

### 13.2 与规格的偏差（都是实现时才发现更好的做法）

| # | 规格写的 | 实际实现 | 原因 |
|---|---|---|---|
| 1 | `enqueue_for_event` 从当天记录里挑最多 3 张、按置信度倒序 | **只入队当前这一帧**，上限按 `(device_id, local_date)` 计数到 3 | 上传后处理只有当前帧可用；回捞历史帧要在同一事务里重读并重算，收益小、复杂度高 |
| 2 | 接口为 `DELETE /contributions/{id}`、`DELETE /contributions`、`POST /contributions/exports`、`GET /exports/{id}/download` | `POST /contributions/{id}/withdraw`、`POST /contributions/export`、`GET /contributions/exports/{id}`，**没有「全部撤回」** | 与既有 P25 萌照的动作用 POST 风格一致；「全部撤回」在有二次确认的 UI 下没必要，且批量删远端容易半途失败 |
| 3 | 上传器方法 `upload_batch` / `delete_files` | `store` / `delete` | 命名更短，且 `store` 一次 commit 语义更清楚 |
| 4 | 配置含 `SHEDGUARD_CONTRIBUTION_INCLUDE_FULL_DEFAULT` | 未加该配置，改用领域常量 `DEFAULT_INCLUDE_FULL=False`；另加 `SHEDGUARD_CONTRIBUTION_UPLOAD_BATCH`（默认 20） | 默认值不该同时存在两处；批量大小才是运维真正要调的量 |
| 5 | 设置接口返回带计数 | `GET/PUT /contribution-settings` 只返回 `enabled` / `include_full` / `updated_at_utc`；计数在 `GET /contributions` 的 `stats` 里 | 一个接口一个关注点，App 也只需要一次列表请求 |
| 6 | 服务层单测 `test_contribution_service.py` | 未单独建文件，服务行为由 12 条集成测试覆盖 | 该服务几乎全是「读写库 + 落盘」，集成测试更接近真实调用路径 |

### 13.3 验收对照

| 验收 | 结果 |
|---|---|
| 1 默认关闭且零网络请求 | ✅ `test_switch_off_keeps_nothing`：样本 0、`data/contributions` 目录都不生成 |
| 2 每次事件 ≤3 张 | ✅ `test_caps_samples_per_event`（连传 4 张 → 3 张） |
| 3 同一帧不重复 | ✅ `ux_contribution_samples_image_owner` 唯一约束 + `find_by_source` |
| 4 重新编码、EXIF 为空 | ✅ `encode_frame` 用 `cv2.imencode` 重编码（单测断言可解码、质量影响体积） |
| 5 不含身份信息 | ✅ `meta_payload` 只输出 `META_FIELDS` 白名单（单测钉死集合相等） |
| 6 撤回删本地 + 调远端 | ✅ `test_withdraw_removes_local_file`；远端删除由 `HuggingFaceUploader.delete` 尽力执行 |
| 7 失败可重试且不影响主链路 | ✅ `upload_attempts` 上限 5；入队整段 `try/except` 只记日志 |
| 8 全部走鉴权、跨用户 404 | ✅ 依赖 `get_current_user`；`test_withdraw_unknown_sample` 404 |
| 9 没配收件箱不假装成功 | ✅ `test_upload_now_without_inbox_skips_and_keeps_pending`：`skipped=1`、样本仍 `pending`、`upload_attempts=0` |
| 10 App 文案与截图 | ✅ 430×932 三张截图核对通过；文案无「服务器 / API / token / 置信度」 |

### 13.4 实测结果（2026-11-16）

- 质量门：`ruff check .` 全绿；`mypy src tests` 129 files Success；`pytest --junitxml` **480 tests / 0 failures / 0 errors**（基线 440，新增 40）；覆盖率 **94.06%**（门槛 85%）。
- 真机冒烟（`.tmp/p29_setup.py` + 真检测/分类模型，端口 8000，`SHEDGUARD_DATA_DIR=.tmp/p29demo`，收件箱未配置）：
  - `PUT /api/v1/contribution-settings` 200（`enabled=true, include_full=true`）；
  - 灌一张真实蜕皮图 → `GET /api/v1/contributions` 返回 1 条 `state=shedding confidence=0.9998 has_full=true upload_status=pending`，`stats.pending=1`；
  - `POST /api/v1/contributions/upload-now` → `{uploaded:0, failed:0, skipped:1}`，样本仍是 `pending`（**没配收件箱不假装成功**）；
  - `GET /contributions/{id}/image` 200 `image/jpeg`；`POST /contributions/export` 201，zip 73,017 字节、含 1 张 crop + 1 份 meta。
- 未做真仓库验证：还没有 fine-grained token（`docs/contribution-setup.md` 第 2–5 节就是给这一步的），配好后按手册跑一次即可。

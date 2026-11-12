# 鉴权与多用户隔离设计（P16）

> 状态：**草案，待批准**
> 日期：2026-11-12
> 上游计划：`docs/plan.md` §3 P16、§4 当前主线
> 关联欠账：`docs/specs/2026-11-02-server-image-ingest-design.md` 第 7 节「无鉴权 / 无 HTTPS / 无隐私留存策略」

## 1. 背景与目标

现状：所有接口零鉴权；`pets` 表没有所有者字段；同一局域网内任何人只要知道地址，就能上传图片、读全部宠物与蜕皮记录、删除别人的数据。单机自用没问题，一旦给第二个人用，就是「互相能看到对方数据」。

本期目标：

1. **匿名设备账号**：App 首次启动自动向服务器注册，拿到一个 token，之后所有请求带上它。用户无感，不需要登录界面。
2. **数据按用户隔离**：宠物及其蜕皮记录、提醒、推送设备都归属于某个用户；非本人访问一律当作不存在。
3. **固件设备令牌**：设备上传图片用独立的设备令牌，不依赖用户账号。
4. **统一的 401 错误契约**，与现有错误码体系一致。

非目标（本期不做，写进 §9 与 plan.md §7）：

- 正式账号体系（邮箱/手机号 + 密码、找回密码、多设备登录）。
- HTTPS / 传输加密（部署层解决，见欠账）。
- 老数据认领（迁移前的宠物归 legacy 用户，App 看不到，见 §5.4）。

## 2. 身份模型

| 主体 | 凭证 | 存放 | 用途 |
|---|---|---|---|
| App 用户 | `user token`（32 字节 `secrets.token_urlsafe(32)`） | 服务端只存 `sha256(token)`；App 存 AsyncStorage | 访问 pets / shed-records / alerts / devices |
| 固件设备 | `device token`（部署时配置的静态串） | 服务端 `SHEDGUARD_DEVICE_TOKEN`；固件 `APP_DEVICE_TOKEN` | `POST /api/v1/images` |

- token 明文只在注册响应里返回一次，服务端永不回显。
- 用户 token 失效（数据库丢失/重置）时，App 收到 401 会清空本地 token 并重新匿名注册——代价是旧数据找不回来，这在「匿名账号」模型下是可接受的，作为已知限制记录。

## 3. 数据模型与迁移 0007

新增表 `users`：

| 列 | 类型 | 说明 |
|---|---|---|
| id | String(36) PK | uuid4 |
| token_hash | String(64) NOT NULL UNIQUE | sha256 十六进制 |
| created_at_utc | String(40) NOT NULL | |
| last_seen_at_utc | String(40) NULL | 每次鉴权成功更新 |

字段改动：

- `pets.owner_id`：String(36) FK `users.id`，NOT NULL，建索引 `ix_pets_owner`。
- `push_devices.owner_id`：String(36) FK `users.id`，NULL（兼容历史行），建索引。
- `alerts` 不加 owner：通过 `pet_id → pets.owner_id` 判定归属，避免第三份冗余。

迁移 `0007_users_and_ownership.py`（`revision="0007"`，`down_revision="0006"`）要点：

1. 建 `users`，插入一条 `id="legacy"`、`token_hash=""` 的占位行（空 hash 永不匹配任何 token）。
2. SQLite 加列必须带默认值：先 `add_column(owner_id, String(36), nullable=True)`，`UPDATE pets SET owner_id='legacy' WHERE owner_id IS NULL`，再用 `batch_alter_table` 改成 `nullable=False` 并建索引。
3. downgrade 反向：删索引、删列、删表。

## 4. 鉴权机制

新增 `infra/auth.py`：`hash_token(raw) -> str`（sha256 十六进制）、`new_token() -> str`。

新增依赖（`api/dependencies.py`）：

- `get_current_user(request, session) -> User`：读 `Authorization: Bearer <token>`；缺失或格式不对 → `UnauthorizedError`；hash 查库未命中 → 同上；命中则更新 `last_seen_at_utc` 并返回。
- `get_optional_user(...)`：无凭证返回 None（给需要「可匿名」的读取接口用，本期不启用）。

新增错误（`errors.py`）：`ErrorCode.UNAUTHORIZED = "UNAUTHORIZED"`；`class UnauthorizedError(ApiError)`，`status_code = 401`。

需要鉴权的路由（在 router 层用 `dependencies=[Depends(get_current_user)]` 或逐个端点声明）：

| 路由组 | 鉴权 |
|---|---|
| `/api/v1/pets*`（含 shed-records、check-photo、shed-prediction） | 用户 token |
| `/api/v1/alerts*` | 用户 token |
| `/api/v1/devices*` | 用户 token |
| `POST /api/v1/images` | 设备 token（`SHEDGUARD_DEVICE_TOKEN`） |
| `GET /api/v1/images/{id}` | 用户 token + 该图所属设备绑定了本人的宠物 |
| `/api/v1/knowledge*`、`/api/v1/risk-assessment`、`/healthz`、`/readyz` | 不鉴权（纯静态/无状态） |

`SHEDGUARD_DEVICE_TOKEN` 为空时：**允许上传但每次启动记一条 WARNING**（本地开发免配），并在 `server/README.md` 的已知限制里写明「未配置设备令牌 = 图像上传接口无鉴权」。

## 5. 多租户过滤规则

原则：**非本人资源一律返回 404，不返回 403**，避免泄露「这条数据存在」。

1. `PetRepository.list(owner_id)`、`get(pet_id, owner_id)`；`PetService.create(owner_id, ...)`。
2. `PetService.get/update/delete` 先校验归属，不符抛 `NotFoundError`。
3. `ShedRecordService` 全部方法先通过宠物归属校验（内部复用 `PetRepository.get(pet_id, owner_id)`）。
4. `AlertRepository.list(..., owner_id)`：用 `pet_id IN (SELECT id FROM pets WHERE owner_id=:uid)` 过滤；`pet_id` 为空的 alert 不出现在任何用户列表中（只能由设备侧查看，本期不做设备侧查看）。
5. `PushDeviceRepository.upsert(...)` 写入 `owner_id`；`list_for` 按 owner 过滤。
6. `check-photo` 与 `POST /images` 归属：check-photo 走宠物归属；设备上传的图不归属用户，`GET /images/{id}` 通过 `push_devices.device_id → pet → owner` 判定。

## 6. 接口变更

新增：

- `POST /api/v1/users/anonymous` → 200 `{"user_id": "...", "token": "..."}`（不鉴权，限流欠账）。
- `GET /api/v1/users/me` → 200 `{"user_id": "...", "created_at_utc": "..."}`（需用户 token，供 App 校验本地 token 是否仍有效）。

所有需鉴权接口新增错误响应：401 `{"error": {"code": "UNAUTHORIZED", "message": "...", "request_id": "..."}}`。

## 7. App 改动

1. `src/lib/auth.ts`：`getToken()/loadToken()/ensureToken()`（无 token 时调匿名注册并持久化）、`resetToken()`；`useAuthReady()`。
2. `src/lib/api.ts`：`apiFetch` 自动附加 `Authorization: Bearer <token>`；收到 401 时清 token 并重试一次（重注册）。
3. `src/app/_layout.tsx`：启动时 `ensureToken()` 完成前显示加载态（或首页骨架），避免并发无 token 请求。
4. `src/app/(tabs)/settings.tsx`：新增「身份」小卡片，显示 user_id 前 8 位 + 「重置身份」按钮（Alert 二次确认，文案说明会丢失本地账号数据）。

## 8. 测试计划

单元：

- `hash_token` / `new_token` 唯一性与长度。
- `get_current_user`：无头、非 Bearer、空 token、未知 token、有效 token、last_seen 更新。
- `PetService` 归属：A 读取 B 的宠物 → `NotFoundError`。

集成（`tests/integration/test_auth.py`）：

- 匿名注册返回 token；`GET /users/me` 带 token 200、不带 401。
- A 建宠物；B 的 token 列表看不到，`GET /pets/{id}` 404，`DELETE` 404。
- 无 token 访问 `/api/v1/pets` → 401 `UNAUTHORIZED`。
- 迁移 0007 upgrade/downgrade 可逆；历史 pets 行 owner_id 为 `legacy`。

门槛：总体覆盖率 ≥85%、业务层 ≥90%；`ruff` 与 `mypy src tests` 全绿。

## 9. 已知限制（写入 plan.md §7 与 README）

1. 仍无 HTTPS：token 在局域网内明文传输，可被抓包。
2. 用户 token 存在 AsyncStorage（明文），手机被 root/越狱可读。
3. 无速率限制：匿名注册接口可被刷，会产生垃圾用户行。
4. 迁移前的历史宠物归 `legacy` 用户，App 无法看到（无认领接口）。
5. 一个用户只能在自己的手机上用；换机/清数据即丢失账号与数据。
6. 设备令牌是全服共享静态串，一个设备泄露则所有设备上传口开放。

## 10. 实施顺序（批准后执行）

1. 迁移 0007 + `users` 表 + `pets.owner_id` / `push_devices.owner_id`。
2. `domain/user.py`（`User` dataclass）+ `infra/auth.py` + `UserRepository`。
3. `errors.py` 加 `UnauthorizedError`；`dependencies.py` 加 `get_current_user`。
4. `routes/users.py`（anonymous / me）。
5. 各路由接入鉴权；`PetService`/`ShedRecordService`/`AlertRepository`/`PushDeviceRepository` 加 owner 过滤。
6. App：`lib/auth.ts` + `apiFetch` + `_layout` + 设置页身份卡片。
7. 测试补齐 → 质量门 → 文档（spec 实现记录、server/README、app/README、handoff、plan §6/§7）→ 原子提交（服务端 / App / 文档分开）。

## 11. 验收标准

1. 不带 token 访问 `/api/v1/pets` 返回 401，错误体含 `UNAUTHORIZED`。
2. 两个不同 token 的宠物数据互不可见（列表、详情、修改、删除四条路径都验）。
3. `POST /api/v1/users/anonymous` 返回 token，且同一 token 可重复使用（`/users/me` 200）。
4. 迁移 0007 在空库与有历史数据的库上都能 upgrade；downgrade 可回退。
5. 固件上传在不配设备令牌时仍可用（记 WARNING）；配了错误令牌时 401。
6. App 首次启动自动注册并可正常建宠物；手动清除 token 后自动重注册。
7. 覆盖率与 lint/类型检查门槛全部通过。
8. 文档四处（spec / server README / app README / handoff）与 plan.md 变更记录同步。

## 12. 实现记录（P16，2026-11-12）

落地文件：

| 层 | 文件 |
|---|---|
| 领域 | `domain/user.py`（`User`）；`domain/pets.py` 与 `domain/alerts.py` 各加 `owner_id` 字段 |
| 基础设施 | `infra/auth.py`（`new_token`/`hash_token`）、`UserRepository`、`UserRow`、迁移 `0007_users_and_ownership.py` |
| 接口 | `api/routes/users.py`（`POST /anonymous`、`GET /me`）；pets/alerts/devices/images 接入鉴权 |
| 依赖 | `api/dependencies.py` 的 `get_current_user`（`auth_enabled=False` 时返回内置 `dev` 用户） |
| 配置 | `auth_enabled`（默认 True）、`device_token`（默认空） |
| 测试 | `tests/unit/test_auth.py`、`tests/integration/test_auth_api.py` |

与规格的偏差（6 条）：

| # | 规格原写 | 实际实现 | 原因 |
|---|---|---|---|
| 1 | 迁移用 `batch_alter_table` 两步改 NOT NULL | `add_column(..., nullable=False, server_default="legacy")` 一步完成 | SQLite 上更简单可靠，效果等价 |
| 2 | 集成测试文件 `test_auth.py` | `test_auth_api.py` | 与单测 `tests/unit/test_auth.py` 同名会触发 pytest 模块导入冲突 |
| 3 | alerts 通过 `pet_id → pets.owner_id` 判定归属 | 列表过滤 `pet_id IS NULL OR pet_id IN (本人宠物)` | 设备级（未绑定宠物）提醒的 `pet_id` 为空，若只按「本人宠物」过滤会全部丢失 |
| 4 | 图片接口用 Bearer 头 | 详情接口额外接受 `?token=` 查询参数 | React Native `<Image>` 无法附加请求头，只能把令牌放进 URL |
| 5 | 未提设备令牌头名 | 头名定为 `X-Device-Token` | 与 `X-Device-Id` 命名一致 |
| 6 | 未提 App 令牌就绪时序 | 提醒详情页先 `ensureToken()` 再渲染图片 | 否则图片 URL 拼不到 `?token=` |

验收结果：353 测试全部通过、覆盖率 95.81%；`ruff` 与 `mypy src tests`（104 文件）全绿；在**已有历史数据的 M12 数据库**上启动服务，迁移 0007 自动升级成功（readyz 200），历史宠物归 `legacy` 用户、新匿名账号看不到；新建宠物 owner_id 正确落库，两个账号互不可见。App 侧 `tsc`/`eslint` 全绿，430px 截图确认设置页「身份」卡片正常（未连接服务器时显示提示、重置按钮禁用）。

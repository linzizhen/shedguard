# App 与新后端接口设计规格（M8 + M9）

> 状态：后端部分已实现（见第 10 节实现记录）
> 日期：2026-11-09
> 关联：`docs/roadmap.md` Phase 4（App）、`docs/specs/2026-11-02-server-image-ingest-design.md`（现有图片接口）

## 0. 背景与产品转向

2026-11-09 产品方向调整：**从「自动监控硬件」转向「手机工具 App」**，固件并行开发。

理由：
- 公开数据里蒙白（pre-shed）样本为零、红外样本为零、跨天时序为零——摄像头自动监控的核心价值（提前预警）纯靠网图数据无法兑现。
- 用户不打算自采数据（无守宫），Phase 2 自采路线取消。
- 现有资产（后端 90% 代码、二态分类器 91% 准确率、知识库第一轮）可以完整复用到 App 产品。
- 长线：App 积累用户贡献照片，蒙白样本够了再回头做硬件的自动预警。

## 1. App 功能范围（MVP）

| 功能 | 描述 | 依赖 |
|---|---|---|
| 拍照查验蜕皮 | 拍一张照片 → 上传 → 分类器判定 shedding/normal → 显示结果与建议 | 现有 `POST /api/v1/images` + `POST /api/v1/shedding/{image_id}` |
| 手动蜕皮日志 | 记录每次蜕皮（开始/结束日期、备注）→ 查看历史 → 预测下次 | 新增后端接口 |
| 护理知识库 | 浏览豹纹守宫饲养知识（温度/湿度/UVB/喂食/蜕皮护理/卡皮处理） | 新增后端接口（静态内容） |
| 卡皮风险评估 | 答问卷（蜕皮完整性/环境湿度/趾部状况等）→ 规则引擎输出风险等级与建议 | 新增后端接口 |

## 2. 技术选型

- **App 框架**：React Native + TypeScript（用户选定）
- **后端**：现有 FastAPI 服务（用户选定）
- **固件**：ESP-IDF + C，并行开发（用户选定，有板子）
- **App 状态管理**：React Query（服务端状态）+ 少量本地状态
- **导航**：React Navigation，底部 Tab（查验 / 日志 / 知识 / 设置）

## 3. 新增后端接口

### 3.1 宠物管理

App 用户需要「宠物」概念来组织蜕皮日志与照片。MVP 不做多用户/鉴权（已知欠账），单机使用。

```
POST   /api/v1/pets                       # 创建宠物 {name, species, morph?, birth_date?}
GET    /api/v1/pets                       # 宠物列表
GET    /api/v1/pets/{pet_id}              # 宠物详情
PUT    /api/v1/pets/{pet_id}              # 更新
DELETE /api/v1/pets/{pet_id}              # 删除（级联删日志与照片关联）
```

表 `pets`：`id`（UUID）、`name`、`species`（默认 `eublepharis_macularius`）、`morph`、`birth_date`、`created_at_utc`、`updated_at_utc`。

### 3.2 蜕皮日志

```
POST   /api/v1/pets/{pet_id}/shed-records       # 记录一次蜕皮 {started_on, completed_on?, notes?}
GET    /api/v1/pets/{pet_id}/shed-records       # 历史列表（按开始日期倒序）
PUT    /api/v1/pets/{pet_id}/shed-records/{id}  # 更新（补结束日期、改备注）
DELETE /api/v1/pets/{pet_id}/shed-records/{id}  # 删除
GET    /api/v1/pets/{pet_id}/shed-prediction    # 预测下次蜕皮窗口
```

表 `shed_records`：`id`、`pet_id`（FK）、`started_on`（date）、`completed_on`（date, nullable）、`notes`、`created_at_utc`、`updated_at_utc`。约束：同一宠物 `started_on` 唯一。

**周期预测算法**（`GET .../shed-prediction`）：
- 取该宠物所有有 `completed_on` 的记录，计算相邻两次的 `started_on` 间隔（天）。
- 少于 2 个间隔 → 返回 `{"predictable": false, "reason": "insufficient_data"}`。
- 2 个以上 → 中位数间隔 ± MAD 作为预测窗口：`next_window_start = last_started_on + (median - mad)`，`next_window_end = last_started_on + (median + mad)`。
- 输出：`{"predictable": true, "median_interval_days": 28, "mad_days": 3, "next_window_start": "2026-12-07", "next_window_end": "2026-12-13", "based_on_cycles": 4}`。

### 3.3 拍照查验（聚合端点）

现有流程需要两次请求（上传 → 分类）。App 端合并为一个端点，减少移动网络下的失败窗口：

```
POST /api/v1/pets/{pet_id}/check-photo    # multipart 上传照片
# 响应：
{
  "image_id": "...",
  "state": "shedding" | "normal" | "unknown",
  "confidence": 0.93,
  "probabilities": {...},
  "advice": "..."   # 按状态给操作建议
}
```

内部实现：调 `IngestService` 存图（device_id 取 `pet-{pet_id}`）→ 调 `SheddingService.analyze` → 组装响应。上传接口幂等（SHA-256），重复照片返回已有结果。

**advice 映射**（中文，来自知识库）：
- `shedding`：它在蜕皮。保持湿度 30–40%（可临时提高到 50%），不要手动撕皮，提供粗糙表面（湿润的躲避穴/杜鹃根）帮它蹭。
- `normal`：看起来不在蜕皮期。继续日常护理即可。
- `unknown`：这张照片无法判断（可能没拍到守宫，或置信度不足）。换个角度再拍一张。

### 3.4 知识库

```
GET /api/v1/knowledge/topics          # 话题列表
GET /api/v1/knowledge/topics/{slug}  # 话题正文（Markdown 或结构化 JSON）
```

内容来源：`docs/gecko-params.md` 已核实的知识 + 蜕皮护理操作指南。MVP 作为静态内容内置在后端（Python dict / JSON 文件），不走数据库。话题清单：

| slug | 标题 |
|---|---|
| `overview` | 豹纹守宫速览（寿命/体长/活动时间） |
| `environment` | 饲养环境（温度梯度/湿度/UVB/垫材） |
| `feeding` | 喂食（频率/钙维补充/饮水） |
| `shedding-basics` | 蜕皮基础（频率/过程/正常时长） |
| `stuck-shed` | 卡皮处理（识别/居家处理/就医指征） |
| `hydration` | 加湿操作（何时加/怎么加/加多少） |

### 3.5 卡皮风险评估

```
POST /api/v1/risk-assessment
# 请求体（问卷答案）：
{
  "pet_id": "...",                  # 可选，用于关联记录
  "last_shed_complete": true/false,  # 最近一次蜕皮是否完整（尾巴/趾尖有残留 = false）
  "environment_humidity": "30-40" | "40-50" | "50-60" | "unknown",  # 平时环境湿度
  "hydration_practice": "regular" | "occasional" | "rarely" | "never",  # 蜕皮期是否加湿
  "toe_condition": "normal" | "swollen" | "discolored",  # 趾部状况
  "eye_condition": "normal" | "retained_spectacle",      # 眼部是否有残留蜕皮
  "shallow_water": true/false        # 是否提供浅水盆
}
# 响应：
{
  "risk_level": "low" | "moderate" | "high",
  "score": 2,
  "factors": [
    {"question": "last_shed_complete", "weight": 3, "detail": "上次蜕皮不完整是卡皮累积的最强信号"},
    ...
  ],
  "advice": ["立即操作: ...", "环境调整: ...", "观察要点: ..."],
  "vet_warning": false   # true = 建议就医
}
```

**规则引擎**（硬编码权重，不搞 ML）：

| 问题 | 答案 | 分数 |
|---|---|---|
| last_shed_complete | false | +3 |
| environment_humidity | 50–60 | +1（过湿） |
| environment_humidity | 30–40 | 0（理想） |
| environment_humidity | unknown | +1 |
| hydration_practice | rarely / never | +2 |
| hydration_practice | occasional | +1 |
| toe_condition | swollen | +3 |
| toe_condition | discolored | +2 |
| eye_condition | retained_spectacle | +3（同时 vet_warning = true） |
| shallow_water | false | +1 |

风险等级：0–1 → low；2–4 → moderate；≥5 → high。`vet_warning` 在 eye_condition 为 retained_spectacle 或 toe_condition 为 swollen 时为 true。

## 4. App 界面结构

```
底部 Tab 导航：
├── 拍照（默认 Tab）
│   ├── 相机预览（react-native-vision-camera）
│   ├── 拍照 → 上传 → 显示结果卡片（状态/置信度/建议）
│   └── 历史查验记录（最近 20 条）
├── 日志
│   ├── 宠物切换（顶部下拉）
│   ├── 蜕皮记录时间线（列表 + 下次预测卡片）
│   └── 新增记录（表单：开始日期/结束日期/备注）
├── 知识
│   ├── 话题卡片列表
│   └── 话题详情（Markdown 渲染）
└── 设置
    ├── 宠物管理（增删改）
    ├── 服务器地址（默认 http://<局域网 IP>:8000）
    └── 关于
```

**拍照 Tab 的查验流程**：
1. 打开相机 → 对准守宫 → 拍照
2. 上传（显示进度）→ 等待分类结果（通常 < 2 秒）
3. 显示结果卡片：大字状态（「正在蜕皮」/「正常」/「无法判断」）+ 置信度 + 建议文字
4. 结果可保存到该宠物的查验历史

## 5. 现有后端的改动

1. **新增表**：`pets`、`shed_records`（迁移 0005）。
2. **新增路由模块**：`api/routes/pets.py`、`api/routes/knowledge.py`、`api/routes/risk.py`。
3. **新增服务**：`services/pets.py`、`services/shed_records.py`（含预测算法）、`services/risk.py`（规则引擎）。
4. **新增领域对象**：`domain/pets.py`（Pet dataclass）、`domain/shed_records.py`（ShedRecord、ShedPrediction）。
5. **复用不动**：图片接入（IngestService）、蜕皮状态识别（SheddingService）、现有序列/信号接口。
6. **不引入用户体系**：单机模式，无鉴权（已知欠账，App 联网走局域网）。

## 6. 固件并行线（M9，独立于 App）

ESP32-S3-EYE + ESP-IDF：

1. **WiFi 配置**：`menuconfig` 里配 SSID/密码（MVP 不做配网 UI）。
2. **拍照定时**：每天固定时刻（默认 08:00）触发，`esp_timer` + NTP 对时。
3. **上传**：JPEG → `POST /api/v1/images`（multipart，`X-Device-Id` 头标识设备）。
4. **补光**：850 nm 红外 LED 常亮（拍照前后各 2 秒，减少夜巡干扰）。
5. **状态指示**：板载 LED——绿色闪烁 = 正常运行、红色 = WiFi 断连、蓝色 = 上传中。
6. **失败处理**：上传失败本地暂存（SPIFFS，最多 7 张），WiFi 恢复后补传。

固件上传的图走现有 `device_id` 体系（如 `esp32-eye-01`），服务端已有的分析/序列/信号/状态识别接口全部自动适用。

## 7. 验收标准

### 后端新增接口
- [ ] 宠物 CRUD 全通，删宠物级联删日志
- [ ] 蜕皮记录 CRUD 全通，同日重复记录被拒（409）
- [ ] 预测：0 条记录返回 unpredictable；1 条返回 unpredictable；3 条以上返回窗口
- [ ] 拍照查验：上传真图返回三态之一 + advice；幂等（同图重复上传返回同结果）
- [ ] 知识库：6 个话题全部可读
- [ ] 风险评估：全 low 答案得 0 分；眼部残留触发 vet_warning
- [ ] 新增代码覆盖率 ≥ 90%，ruff + mypy 全绿

### App
- [ ] 四个 Tab 全部可用
- [ ] 拍照 → 结果展示全流程 < 5 秒（局域网）
- [ ] 日志增删改查 + 预测卡片显示
- [ ] 知识库 6 话题渲染正确
- [ ] 风险评估问卷提交后显示等级与建议

### 固件
- [ ] 上电 → 连 WiFi → NTP 对时 → 定时拍照 → 服务端收到图
- [ ] WiFi 断连后恢复能补传

## 8. 已知欠账（本期不做）

- 多用户与鉴权（App 与后端同局域网使用）
- HTTPS（局域网内 HTTP）
- App 推送通知（蜕皮预测窗口提醒，后续版本）
- 蒙白分类（等用户数据积累后训练三态模型）
- 固件 OTA 升级
- 配网 UI（用 menuconfig 硬编码）

## 9. 实施顺序

1. 后端新增接口（pets → shed-records → prediction → check-photo → knowledge → risk）
2. App 骨架（导航 + 网络层 + 宠物管理）
3. App 四功能逐个实现
4. 固件骨架（WiFi + 拍照 + 上传）
5. 固件定时与补光
6. 端到端联调

## 10. 实现记录（M8 后端部分，2026-11-09）

后端六组接口全部实现完毕，319 测试全绿（新增 56 条），覆盖率 96.79%，ruff 与 mypy（87 source files）全绿，真机冒烟通过（迁移 0001→0005 自动执行，六组接口全链路验证）。

### 10.1 与规格的偏差

| 规格 | 实现 | 原因 |
|---|---|---|
| `services/shed_records.py`、`services/risk.py`、`domain/shed_records.py` 分文件 | 合并为 `services/pets.py`、`domain/pets.py`、`domain/risk.py`、`domain/knowledge.py` | pets/shed-records/check-photo 共享 Protocol 与 ADVICE 映射，拆开反而要互相 import |
| 预测「少于 2 个间隔 → insufficient_data」 | ≥3 条**完整**记录（2 个间隔）才 predictable，reason 是完整中文句子 | 与 M6 判定层「样本不足」的表达方式对齐 |
| 风险问卷的 `pet_id` 可选字段 | 去掉 | 评估是无状态规则，不落库，关联没有意义 |
| 风险问卷字段名 `last_shed_complete: bool` 等 | 改为六个单选枚举（`complete/partial/stuck/unknown` 等） | bool 无法表达「不知道」；枚举与 App 问卷 UI 一一对应 |
| `shallow_water: bool` | `water_bowl: fresh_daily / stale_or_absent` | 同上，且问法从「是否提供」改为「水碗状态」更贴近实际 |
| 新增 `CONFLICT` 409 错误码 | 规格没提 | 同宠物同开始日是业务冲突，不是参数错误 |

### 10.2 验收对照

| 验收项 | 结果 |
|---|---|
| 宠物 CRUD 全通，删宠物级联删日志 | ✅ 冒烟验证 204 → records 404 |
| 同日重复蜕皮记录被拒 409 | ✅ 集成测试 + 冒烟 |
| 预测：0/1 条 unpredictable，≥3 条返回窗口 | ✅ 单元 6 条 + 集成 3 条 + 冒烟（中位 27 天、窗口 11-18~11-24） |
| 拍照查验返回三态 + advice，幂等 | ✅ 集成 6 条 + 冒烟（shedding 0.9985 + 中文建议） |
| 知识库 6 话题可读 | ✅ 冒烟列表 + 详情 + 404 |
| 风险评估 low/high/vet_warning | ✅ 单元 14 条 + 冒烟（healthy=low 0，worst=high 8） |
| 新增代码覆盖率 ≥90% | ✅ 总体 96.79%，新模块 91–100% |

### 10.3 已知限制

- `check-photo` 里照片与宠物的关联只体现在 `device_id = pet-{pet_id}` 命名约定上，没有单独的关联表；换宠物名不影响，但换 device_id 规则会断历史。
- 预测算法用的是全部完整记录的间隔中位数，没有做新旧间隔加权（近期蜕皮间隔变化大时预测会偏保守）。
- 知识库是硬编码 Python dict，改内容要改代码发版。

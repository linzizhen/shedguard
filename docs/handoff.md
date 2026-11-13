# 交接文档

> 这份文档给「新会话」或「接手的人」看：项目现在在哪、做过什么决定、下一步做什么。
> 读完这一份，就能接着干，不用翻旧对话。
> 操作规范与代码标准见 `AGENTS.md`，本文只记录项目状态与决策。

## 项目一句话

shedguard：给爬宠主人的蜕皮管理工具。**主线是手机 App**（拍照查验蜕皮状态 + 手动蜕皮日志 + 护理知识库 + 卡皮风险评估），**设备自动监测并行开发**——摄像头在白天固定机位定时抓拍上传，服务端判定「是否正在蜕皮」，一旦检测到蜕皮白皮就推送提醒。第一版只支持干燥型地栖守宫（豹纹、肥尾）。

> 2026-11-11 产品收缩：**弃用「下次蜕皮预测」**（个体周期数据凑不出统计量），改为「看到蜕皮白皮就提醒」的单图检测闭环。

## 当前阶段

**Phase 1 完成（M1→M7）+ M8 App 配套后端接口 + M9 App 骨架 + M10 App 四屏 + 网络图复核重训 v2 + M11 蜕皮检测提醒链路（服务端一期）完成——后端能收图、去重、归档、按天查询、收敛成序列、记录蜕皮事件、对单帧算出体表指标、按时序判定异常、对每张图识别蜕皮状态；App 提供宠物档案、手动蜕皮日志、拍照查验、知识库、风险评估五组接口（预测接口保留但标 Deprecated）；**上传图片后服务端自动跑「指标 → 状态判定」，判定为「正在蜕皮」且状态发生跃迁时生成 alert 并通过 Expo 推送**，另有 devices 注册/注销与 alerts 查询/已读接口。App（Expo SDK 58 + React Native + TypeScript）三 Tab 完成：拍照、蜕皮记录、我的（知识页收进「我的 → 蜕皮知识」），另有卡皮风险评估问卷页与三步首次向导。分类器 v2 测试准确率 0.9286。**固件骨架（Phase 3 一期）已完成：ESP-IDF v5.4.4 工程，WiFi/NTP/板载 OV2640/白天窗口定时抓拍/multipart 上传/SPIFFS 补传队列，`idf.py build` 编译通过（未上板实测，手边无实物）。App 已完成 M12 提醒链路接入：日志屏蜕皮提醒横幅 + 提醒详情页（抓拍原图、自动已读）、`expo-notifications` 推送注册与 `POST /api/v1/devices`、设置屏设备编号绑定宠物。下一步：固件上板联调。**2026-11-12 完成 P16 鉴权与多用户隔离**：匿名账号（`POST /api/v1/users/anonymous`）+ Bearer 令牌，宠物/日志/提醒按用户隔离，App 增加「身份」卡片与 401 自动重注册，固件上传改走共享设备令牌。**同日完成 P17 设备健康兜底提醒**（`device_silent` / `no_detection` 两类提醒 + 后台每 10 分钟扫描）、**P19 CI 修复**（根因是 `requirements.lock` 指向本地合成的非公开版本，CI 改为按 pyproject 区间安装）、**P18 仓库侧就绪**（`app/eas.json` 三 profile、`expo-dev-client`、Android 明文流量开关、`docs/push-setup.md` 手册，待 EAS 构建装机）、**P21 App 新手向交互重做**（三步向导、四 Tab 降三 Tab、拍照页只留一个圆形大按钮、结果页只说人话结论、服务器地址与身份重置收进「高级设置」、知识页移出 Tab）。**无实物可做的收尾项已全部清空**，剩余 P11 固件上板联调、P12 真实数据采集、P18 真机推送、P20 真机自测均需实物或真机。**

公开数据调研已完成（见 `docs/data-survey.md`），结论是全世界都不存在「守宫蜕皮时序」数据集，自采是唯一路径。Roboflow 的 `capstone-habql/gecko_1`（1,163 张，Public Domain）已下载到 `data/raw/gecko1/`。它**能**训「守宫在哪」与「皮是否正在掉」，但**不能**训「蒙白」——标注里的蜕皮样本全是皮已掀起的瞬间，没有一张静止蒙白态；而且分辨率与类别强耦合（短边 < 400px 占 90.9%，蜕皮样本几乎全在高清微距图上），直接做三分类会退化成「白背景 + 高清 = 蜕皮」的捷径学习，所以拆成检测器与状态分类器两个模型分别训。

2026-11-09 又做了一轮全网搜索（见 `docs/data-search-2026-11-09.md`）：确认 Kaggle、GitHub、HuggingFace、Zenodo、iNaturalist 上都不存在蜕皮状态标注数据集；从 B 站蜕皮视频（抽帧）、搜狗图片、iNaturalist 收集到 417 张新图片存 `data/collected/`（不入库），全部可见光、无蒙白标注，作为候选池待人工筛选后扩充训练集。蒙白与红外数据依然为零，自采仍是唯一路径。

2026-11-13 又用 Bing 图片搜索补了一轮：元数据 1052 条、下载 512 张，人工删 50 张（重复/AI 图/睫角守宫）后移出 22 张非活体（3D 打印模型、陶土雕塑、扭蛋摆件、游戏截图、图文海报），**剩 436 张**，采集库合计 779 张。这批图里有大量「白底玩具/摆件」被检测器以 0.78–0.91 的高置信度判成守宫，是「确定的错」的典型来源，清洗时已剔除。

后端现状（`server/`）：配置校验（37 个 `SHEDGUARD_*` 项）、结构化 JSON 日志与 `request_id` 贯穿、统一错误契约、`/healthz` 与 `/readyz`、`POST /api/v1/images`（multipart 或裸 body、SHA-256 幂等）、`GET /api/v1/images`（按天分页）、取原图与元数据、`GET /api/v1/series`（每日代表帧与缺失日）、`PUT/GET /api/v1/shed-events`、`POST /api/v1/analysis/{image_id}`（六项体表指标 + 曝光归一化）、`GET /api/v1/series/{device_id}/signals`（稳健 Z 分数与四状态判定）、`POST /api/v1/shedding/{image_id}`（蜕皮状态识别）、`GET /api/v1/series/{device_id}/shedding`（逐日状态与事件推导）；**App 配套六组**：`/api/v1/pets`（CRUD + 级联删除）、`/api/v1/pets/{id}/shed-records`（CRUD + 同日 409）、`/api/v1/pets/{id}/shed-prediction`（中位数±MAD 窗口预测）、`/api/v1/pets/{id}/check-photo`（上传+分类+建议一次完成）、`/api/v1/knowledge/topics`（6 话题静态知识库）、`/api/v1/risk-assessment`（卡皮风险规则引擎）；**提醒链路**：`POST/DELETE /api/v1/devices`（推送 token 注册/注销）、`GET /api/v1/alerts`、`PATCH /api/v1/alerts/{id}`（标记已读），上传后由 `SHEDGUARD_AUTO_PROCESS` 触发后台 `process_image` 自动完成指标+状态并生成 alert（`SHEDGUARD_PUSH_ENABLED` 控制是否真推）；**鉴权**：`POST /api/v1/users/anonymous`（领取匿名令牌）、`GET /api/v1/users/me`，业务接口要求 Bearer，非本人资源返回 404，固件上传用 `X-Device-Token` 校验 `SHEDGUARD_DEVICE_TOKEN`；**设备健康兜底**：后台每 10 分钟扫描，设备静默超 6 小时或连续 5 次未检出守宫时生成 `device_silent` / `no_detection` 提醒；Alembic 七次迁移在启动时自动升级、CI 与 pre-commit。**400 个测试，覆盖率 95.29%**，ruff 与 mypy strict 全绿。

定位模型（`ml/`）：`yolov8n` 微调 50 轮（RTX 5070 上 3.6 分钟），单类别 `gecko`，测试集 `mAP50 = 0.902 / mAP50-95 = 0.578`，通过 0.85 验收线。导出 `ml/models/gecko-det.onnx`（12.2 MB，不进仓库），已用服务端 `OnnxDetector` 加载真实网图验证，8/8 检出。已知短板：训练集全是可见光，一张红外图都没有。

状态分类器（`ml/`）：`resnet18` 微调 15 轮（约 2 分钟），任务是给检测框裁出的守宫判定蜕皮阶段。**当前只有二态**（`normal` / `shedding`），因为公开数据里蒙白样本是零。基线 v1（`gecko-state.onnx`）测试集准确率 0.911、`shedding` 召回 0.781。2026-11-11 把 343 张网络图人工复核后（只留 88 张干净豹纹守宫图）并入训练集重训出 **v2（`gecko-state-v2.onnx`）**，留出测试集准确率升到 **0.9286**、`shedding` 召回 **0.8125**，作为新推荐模型。导出 `.labels.json`，服务端从它读类别顺序，换模型只需换文件、不改代码。真机冒烟：8 张图 7 张判对，1 张置信度 0.513 被降级为 `unknown`。

2026-11-13 试了 **v3（`gecko-state-v3.onnx`，未部署）**：把 Bing 那 436 张里置信度极端的 298 张并入 train。结果召回上去、精确率下来——测试集蜕皮召回 0.8125 → **0.9062**，但精确率 0.9286 → **0.7838**（正常日约每 10 天误报 1 次），总体准确率 0.9286 → 0.9018。原因是新图的标签是 v1 模型自己预测的，等于把它的误差写进了训练集。**结论：线上继续用 v2，v3 只留档**。同一轮扫描还发现 v2 在 `p(shedding) ≥ 0.80` 时测试准确率 0.9464、精确率 0.9643，优于默认 argmax；但 P22 证明模糊图上置信度会虚高，所以暂不改服务端默认阈值。

**2026-11-13 完成 P22–P24 工程加固**（用户要求「不用手机也能推进」）。**P22 鲁棒性测试与阈值标定**：`ml/eval_robustness.py` 对 461 张图做 21 档退化（分辨率、JPEG、模糊、亮度/噪声、玻璃反光 + 组合退化），共 9681 次推理，报告在 `docs/robustness-2026-11-13.md`。核心结论：同源网图的 0.9286 不代表真实场景——组合退化下 valid 蜕皮召回 0.9231 → 0.6374、test 0.8438 → 0.6562；离焦最伤（模糊核 7 时 valid 召回只剩 0.3626）；**且模糊越重平均置信度反而越高（0.9557 → 0.9770），说明抬高 `state_min_confidence` 拦不住漏报，只会把「确定的错」留在正常类里**。因此本轮**不改**服务端默认阈值，阈值语义（abstain vs `p(shedding) ≥ T` 判定线）列为待真机数据决定。**P23 照片保留策略**：`services/retention.py`，`SHEDGUARD_IMAGE_RETENTION_DAYS` 默认 0（永久保留）；开启后先删磁盘文件再删数据库行，连带清 `frame_metrics`/`shedding_states`，提醒只解除图片引用不整条删。**P24 请求速率限制**：`api/ratelimit.py` 内存令牌桶（key = IP + Authorization 摘要前 12 位），每 60 秒清扫旧 key，`/healthz`、`/readyz`、`/docs`、`/openapi.json` 豁免，超限 429 `RATE_LIMITED`；默认 `SHEDGUARD_RATE_LIMIT_PER_MINUTE=0` 关闭。服务端测试 370 → **400**、覆盖率 95.29%。

## 已经定下来的决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 产品切口 | 蜕皮识别 | 卡皮会导致趾头/尾巴坏死甚至死亡；现有产品只解决环境稳定 |
| 不做 | 自动喂食、控温湿、整箱产品、诊断 | 喂食是玩家唯一乐趣；整箱要打供应链价格战 |
| 硬件 | ESP32-S3-EYE + 红外补光 + 支架 | 已有板子；守宫晨昏活动，OV2640 夜拍全黑，必须红外 |
| 形态 | 外挂（夹在玻璃上），不做整箱 | 成本低，不改变用户现有饲养方式 |
| 核心算法 | 固定机位 + 每日对比 + 时序判断 | 不做单张照片识别（不可靠） |
| 产品切口收缩 | 从「提前 2–5 天预测」收缩为「识别蜕皮状态并提示」 | 预测需要个体周期基线，而蜕皮频率连公开资料都没有一致值（跨度 5 天到 2 个月）；状态识别能立刻做出可用产品，预测等真实数据积累后再上 |
| 状态识别架构 | 检测器出框 → 裁剪 → 独立分类器判状态 | 状态定义会反复改（二态 → 三态 → 可能分卡皮），捆进检测器则每改一次就要重训检测器；分开后检测器半年不用动 |
| 状态输出 | 四态：`normal` / `opaque` / `shedding` / `unknown` | 「已蜕完」不是视觉状态而是状态转换事件，由服务层推导；`unknown` 是服务层判定，模型不能直接输出 |
| 产品方向 | 手机 App 为主线交付物，固件并行开发 | 用户不自采数据（无守宫），蒙白/红外/时序全为零，硬件自动预警做不了；App 能立刻复用现有分类器+知识库交付价值，用户使用中积累数据 |
| App 技术栈 | React Native + TypeScript，后端沿用 FastAPI，固件 ESP-IDF (C) | 用户选定 |
| 第一版范围 | 只支持干燥型地栖守宫（豹纹、肥尾） | 饲养参数统一，先做深再扩展 |
| 名字 | shedguard | 曾考虑「守蜕」，因谐音 sorry 被否 |
| 技术分层 | 事实层（传感器/记录）→ 标准层（知识库）→ 判断层（AI+规则） | 灌知识用 RAG，不用微调 |
| 代码标准 | 商业级工程标准（分层、类型、测试、日志、错误契约、版本化迁移） | 项目要长期演进，底子在第一个模块就定下来 |

## 目录结构

```
shedguard/
├── AGENTS.md                 # AI 代理与接手者的操作手册（先读这个）
├── README.md                 # 产品介绍（对外）
├── docs/
│   ├── product.md            # 产品定位、MVP 边界、非目标、风险
│   ├── gecko-params.md       # 豹纹守宫参数表（已核实第一轮，每条带来源）
│   ├── shed-detection.md     # 蜕皮识别思路与验证方法
│   ├── data-survey.md        # 公开数据可获得性调研（结论：必须自采）
│   ├── data-search-2026-11-09.md # 全网搜索记录（417 张新图，蒙白仍为零）
│   ├── handoff.md            # 本文件
│   ├── plan.md               # 唯一权威计划（里程碑、当前主线、变更记录）
│   ├── roadmap.md            # 早期规划存档（2026-11-12 作废，勿据此开发）
│   └── specs/
│       ├── 2026-11-02-server-image-ingest-design.md   # 后端图片接入服务设计规格
│       ├── 2026-11-02-series-and-events-design.md     # 每日序列与蜕皮事件设计规格
│       ├── 2026-11-02-shed-detection-core-design.md   # 蜕皮识别三层架构（定位/信号/时序）
│       ├── 2026-11-02-shed-judgement-design.md        # 时序判定层（稳健 Z 分数与告警状态机）
│       ├── 2026-11-04-shedding-state-design.md        # 蜕皮状态识别（四态、事件推导、分类器接入）
│       ├── 2026-11-09-app-and-firmware-design.md      # App 与固件配套（六组新接口、App 界面、固件任务）
│       └── 2026-11-11-shedding-alert-pipeline-design.md # 蜕皮检测提醒链路（自动流水线、alert、Expo 推送、固件抓拍）
├── .github/workflows/ci.yml  # GitHub Actions：ruff + mypy + 覆盖率
├── .pre-commit-config.yaml   # 本地提交前钩子
├── data/
│   ├── raw/gecko1/           # Roboflow gecko_1 原始数据（1,163 张，不入库）
│   └── collected/            # 2026-11-09 全网搜索收集的新图（417 张，不入库）
├── ml/
│   ├── README.md                     # 两个模型的数据集构建、训练、产物与已知限制
│   ├── requirements.txt              # torch / torchvision / ultralytics（仅训练机）
│   ├── prepare_detection_dataset.py  # 分割标注 → 检测框，构建单类别数据集
│   ├── train_detector.py             # 训 YOLOv8n 并导出 ONNX
│   ├── build_state_dataset.py        # 按「有无蜕皮标注」裁剪出二态分类数据集
│   ├── train_state_classifier.py     # 训 resnet18/mobilenet 并导出 ONNX + labels.json
│   ├── datasets/gecko-det/           # 检测数据集（1,120 图 / 1,124 框，不入库）
│   └── datasets/gecko-state/         # 状态数据集（845 正常 / 275 蜕皮，不入库）
├── firmware/                 # ESP32-S3-EYE 固件（ESP-IDF v5.4.4：WiFi/NTP/相机/上传/补传，已编译未上板）
│   ├── main/                 # main.c + wifi/time_sync/camera/uploader/backlog + app_config.h
│   ├── partitions.csv        # 8MB 分区（含 storage SPIFFS 补传区）
│   └── sdkconfig.defaults    # esp32s3 + 8MB Octal PSRAM + 自定义分区表
├── server/                   # 后端服务（图片接入、分析、判定、状态识别、App 接口、提醒链路全部完成）
│   ├── README.md             # 运行、接口、配置与开发说明
│   ├── pyproject.toml        # 依赖、ruff、mypy、pytest、覆盖率配置
│   ├── alembic.ini           # 迁移配置
│   ├── requirements.lock     # 完整依赖锁定
│   ├── .env.example          # 配置样例
│   ├── src/shedguard_server/ # api、domain、services、infra、migrations
│   └── tests/                # unit 与 integration
└── app/                      # React Native App（Expo SDK 58，三 Tab + 首次向导 + 提醒链路已完成）
    ├── src/app/              # Expo Router：三 Tab + 首次向导 + 宠物表单 + 知识列表/详情 + 风险评估 + 提醒详情
    ├── src/components/       # ui.tsx 黏土风基础件 + PetForm + PetPicker
    ├── src/hooks/            # usePets / useShed / useKnowledge / useRisk / useAlerts（React Query）
    └── src/lib/              # theme / api / auth / serverUrl / deviceId / onboarding / resultCopy / types / dates
```

## 下一步（按顺序）

> 唯一权威计划见 [plan.md](plan.md)。本节与 plan.md 冲突时，**以 plan.md 为准**；计划有变先改 plan.md。

分阶段计划、依赖关系与验收标准见 `docs/plan.md`（唯一权威），这里只列最近几步：

1. ~~后端图片接收服务（Phase 0–1）~~ —— 已完成：M1 骨架、M2 图片接入、M3 每日序列与蜕皮事件、M5 信号层
2. ~~M4 定位模型训练~~ —— 已完成：测试集 mAP50 0.902，ONNX 已接入服务端并验证
3. ~~M6 时序判定层~~ —— 已完成：`GET /api/v1/series/{device_id}/signals`，稳健 Z 分数 + 四状态机
4. ~~M7 蜕皮状态识别~~ —— 已完成：检测 → 裁剪 → 分类，二态模型（`normal` / `shedding`）准确率 0.911，服务端四层打通
5. ~~导出 Roboflow `capstone-habql/gecko_1`~~ —— 已完成，落在 `data/raw/gecko1/`
6. ~~M8 App 配套后端接口~~ —— 已完成：宠物/日志/预测/拍照查验/知识库/风险评估六组，319 测试全绿，真机冒烟通过（见规格第 10 节实现记录）
7. ~~M9 App 骨架~~ —— 已完成（`9c3458c`）：Expo SDK 58 + Expo Router + React Query，四 Tab 导航、`apiFetch` 网络层（对齐后端错误契约）、设置屏（服务器地址保存/测试连接 + 宠物 CRUD）完整实现，`tsc --noEmit` 与 `eslint` 全绿
8. ~~App 逐屏补功能~~ —— 已完成（M10）：拍照查验（expo-image-picker → `check-photo` 接口 → 结果卡片，四态徽章 + 概率条 + 护理建议）、蜕皮日志（预测窗口卡片 + 记录时间线 + 添加/标记完成/删除 + 风险评估入口）、知识（六话题列表 + 详情页）、卡皮风险（六题问卷 → 评分分级 + 就医警示）；`tsc --noEmit` 与 `eslint` 全绿，Expo Web 预览逐屏截图验证通过
9. ~~ESP-IDF 固件骨架（Phase 3 一期）~~ —— 已完成：`firmware/` 下 ESP-IDF v5.4.4 工程，WiFi STA 自动重连 → SNTP 对时 → 08:00–20:00 每 30 分钟抓拍 VGA JPEG（板载 OV2640）→ multipart `POST /api/v1/images`（`X-Device-Id`/`X-Captured-At`）→ 失败入 SPIFFS 队列（≤7 张）每分钟补传；`idf.py build` 通过（约 1.06 MB，app 分区 75% 空闲）。**未上板实测**，上板后需验相机/窗口/补传。规格见 `docs/specs/2026-11-11-shedding-alert-pipeline-design.md` §4
10. ~~人工复核 `data/collected/` 的新图并重训~~ —— 已完成（2026-11-11）：343 张落盘图经裁剪+聚类 325 簇，人工只留 88 张干净豹纹守宫图（normal 68 + shedding 20），并入 train 重训出 `gecko-state-v2`，留出测试集 0.9107 → 0.9286。多数网络图是别的物种/皮屑特写/远景，可用量很低；蒙白仍为零
11. **补蒙白样本** —— 现有公开数据里蒙白图是零，三态跑不起来。App 上线后靠用户拍照积累，或后续自采
12. ~~知识库核实（Phase 9）~~ —— 第一轮已完成：全部条目换成带来源的值，修正 8 处错误（最要紧的是「需要 UVB」「日常湿度 30–40%」「蜕皮频率无一致来源」）。剩余 5 项需真实个体数据
13. ~~M11 蜕皮检测提醒链路（服务端一期）~~ —— 已完成：上传后自动跑指标+状态，状态跃迁生成 alert 并 Expo 推送；新增 devices/alerts 四个接口与迁移 0006，339 测试 / 覆盖率 95.97% 全绿，真机冒烟通过（见规格 §15）
14. ~~M12 App 接入提醒链路~~ —— 已完成：日志屏删预测卡片、顶部加蜕皮提醒横幅（拉 `GET /api/v1/alerts`，未读红点，点开进详情页看抓拍原图并自动标已读）；`expo-notifications` 注册 token 并 `POST /api/v1/devices`，收到推送即刷新提醒列表；设置屏新增「摄像头与提醒」卡片（设备编号 + 绑定宠物 + 保存并启用通知）。`tsc`/`eslint` 全绿，Expo Web 逐屏截图验证通过
15. **固件上板联调** —— 手边无实物；上板后验相机出图、白天窗口、SPIFFS 补传，并与服务端真实端点对接
16. ~~P16 鉴权与多用户隔离~~ —— 已完成（2026-11-12）：匿名账号令牌（`POST /api/v1/users/anonymous` + Bearer，服务端只存 sha256）、`pets.owner_id` 按用户隔离（非本人资源返回 404）、固件上传走 `X-Device-Token`；迁移 0007；App 加 `lib/auth.ts`（401 自动清 token 重注册）与设置页「身份」卡片。353 测试 / 覆盖率 95.81% / ruff+mypy 全绿；在已有历史数据的库上验证过迁移回填（历史宠物归 `legacy`）
17. ~~P17 掉线与无检出兜底提醒~~ —— 见第 18 项
18. ~~P17 设备健康兜底提醒~~ —— 已完成（2026-11-12）：新增 `device_silent` / `no_detection` 两类提醒，后台每 10 分钟扫描已注册设备（活跃时段内静默 6 小时、连续 5 次未检出）；`AlertService.create_alert` 通用化并支持按 kind 推送；App 日志横幅与详情页按 kind 显示。365 测试 / 覆盖率 95.94% / ruff+mypy 全绿
19. ~~P19 CI 版本验证~~ —— 已完成（2026-11-12）：根因是 `requirements.lock` 从本地 Python 3.14 freeze 出的合成版本（如 `numpy==2.5.4`）在公开 PyPI 并不存在；CI 改为 `pip install -e ".[dev]"` 按 `pyproject.toml` 区间解析，`requirements.lock` 仅作本地复现记录；已实测 cp312 / cp313 的 linux 轮子齐全（numpy 2.2.6、opencv-python-headless 5.0.0.93、onnxruntime 1.31.1）
20. **P18 推送真链路** —— 当前主线（需一台真手机）：仓库侧已就绪（`app/eas.json`、`expo-dev-client`、Android 明文流量开关、`docs/push-setup.md` 手册）。待你在自己机器上 `eas login` + `eas init` + `eas build -p android --profile development`，装到手机后在设置页点「保存并开启通知」，再按手册第 5 节验证真实推送；随后 P20 真机自测
21. ~~P21 App 新手向交互重做~~ —— 已完成（2026-11-12）：三步向导（欢迎 → 起名字 → 开始，可跳过）、四 Tab 降为三 Tab（拍照 / 蜕皮记录 / 我的）、拍照页只留 200px 圆形大按钮 + 一句提示、结果页只显示「结论 + 建议 + 两个按钮」（置信度与概率收进折叠的「看看更多细节」）、知识页从 Tab 移到「我的 → 蜕皮知识」、服务器地址与身份重置收进折叠的「高级设置」。`tsc`/`eslint` 全绿，430×932 逐屏截图核对通过。规格见 `docs/specs/2026-11-12-novice-ux-redesign.md`
22. ~~P22 鲁棒性测试与阈值标定~~ —— 已完成（2026-11-13）：`ml/eval_robustness.py` 21 档退化 × 461 张图 = 9681 次推理，报告 `docs/robustness-2026-11-13.md`。组合退化下 valid 蜕皮召回 0.9231 → 0.6374、离焦（核 7）只剩 0.3626；模糊越重平均置信度反而越高（0.9557 → 0.9770），证明抬 `state_min_confidence` 无法提升召回。未改默认阈值，阈值语义列为待真机数据决定
23. ~~P23 照片保留策略~~ —— 已完成（2026-11-13）：`SHEDGUARD_IMAGE_RETENTION_DAYS`（默认 0 永久保留）；开启后按拍摄时间清理，先删文件再删行、连带清 `frame_metrics`/`shedding_states`、提醒只解除图片引用；lifespan 每 6 小时跑一次
24. ~~P24 请求速率限制~~ —— 已完成（2026-11-13）：`SHEDGUARD_RATE_LIMIT_PER_MINUTE`（默认 0 关闭）+ `RATE_LIMIT_BURST`；内存令牌桶按 IP + 令牌摘要分桶，旧 key 定期清扫，健康检查与文档豁免，超限 429 `RATE_LIMITED`。服务端 400 测试 / 覆盖率 95.29% / ruff+mypy 全绿

> 为什么先后端：固件的上传目标必须先存在。否则板子写完了也没有真实端点可发，联调只能对着假想端点做，问题会一直拖到集成时才暴露。

## 环境注意

- 这台机器的 Git 自带 `sh.exe` 在沙箱里起不来，推送前需要先跑：
  ```powershell
  $env:GIT_SSH = "C:/windows/System32/OpenSSH/ssh.exe"
  $env:GIT_SSH_VARIANT = "ssh"
  ```
- 远端：`git@github.com:linzizhen/shedguard.git`
- 本机没有可用的全局 `python` 命令（只有 Microsoft Store 占位别名），执行 Python 相关命令需显式指定解释器。
- 显卡是 RTX 5070（12 GB，compute capability 12.0）。**PyPI 上的 Windows `torch` 是纯 CPU 版**，训练必须从 PyTorch 官方源装 CUDA 版：`--index-url https://download.pytorch.org/whl/cu130`，且要显式写 `torch==2.14.1+cu130`（该通道最高只到 2.14.1，不写版本号 pip 会认为已装的 2.15.0 更新而跳过）。
- **YOLO 训练必须以完整权限运行**：`ultralytics` 在扫标签缓存与建 DataLoader 时用 `multiprocessing` 创建命名管道，沙箱 `workspace-write` 模式报 `PermissionError: [WinError 5]`。
- 训练前把缓存目录指向仓库内：`$env:MPLCONFIGDIR=".tmp\mpl"`（默认写 `C:\Users\...\.matplotlib`，沙箱只读）、`$env:YOLO_CONFIG_DIR=".tmp\ultralytics"`、`$env:TORCH_HOME=".tmp\torch"`。
- **torch 2.14 的 ONNX 导出需要 `onnxscript`**，缺了直接 `ModuleNotFoundError`；且它会把权重写成同名的 `.onnx.data` 并在临时目录 `rmdir`，沙箱下报 `PermissionError: [WinError 5]`。所以导出类训练命令要加完整权限，并让脚本把外部权重内联回单文件。
- **启动服务用 `python -m shedguard_server`，不是 `uvicorn shedguard_server.app:app`**——模块里只有 `create_app` 工厂，没有模块级 `app`。需要 `$env:PYTHONPATH="D:\shedguard\server\src"`。
- `pytest -q` 的最终统计行在 PowerShell 管道里会丢，要拿准确数字用 `pytest --junitxml=<file>` 再读 XML。
- 含中文的源文件不能用 `Get-Content -Raw` / `Set-Content` 管道改写（默认按 GBK 解码，写回即乱码），一律用编辑工具。
- 机器上设了指向 `127.0.0.1:7897` 的 `HTTP_PROXY`/`HTTPS_PROXY`，但代理常没在跑。所有 `pip` 与 `httpx` 命令前要清空这些变量，`httpx` 还要 `trust_env=False`。
- **ESP-IDF 固件构建**：本机 ESP-IDF v5.4.4 在 `C:\Espressif\frameworks\esp-idf-v5.4.4`，python 在 `C:\Espressif\python_env\idf5.4_py3.11_env\Scripts`，git 在 `C:\Espressif\tools\idf-git\2.44.0\cmd`。PowerShell 执行策略挡 `export.ps1`，且 `export.bat` 找不到 python（本机无全局 python）——要先把上面 python/git 目录加进 `PATH` 再 `call export.bat`。`.tmp/idf.bat` 是现成的封装：`cmd /c "D:\shedguard\.tmp\idf.bat idf.py build"`。首次 `set-target` 会从组件注册表下载 `esp32-camera`，构建必须在完整权限（danger-full-access）下跑，因为它要写 `C:\Espressif`。

## 待确认

- [x] ~~是否先买一只豹纹守宫~~ —— 已定：不买，先用公开数据与手机自采起步
- [x] ~~数据自采的机位与频次（手机临时机位）~~ —— 已被 m04706 决策取代：不自采，App 拍照查验是数据入口，靠使用积累
- [x] ~~后端规格的三个技术决策~~ —— 已定：FastAPI + SQLAlchemy + Alembic、`/api/v1`、默认监听 `127.0.0.1`
- [x] ~~开发阶段先做固件还是先做后端图像分析~~ —— 已定：先后端接收端点
- [x] ~~是否注册 Roboflow 账号导出 `capstone-habql/gecko_1`~~ —— 已定：已导出并评估，只用作定位训练集
- [ ] 判定层的阈值怎么校准 —— 当前 `z ≥ 2.0`、连续 2 天、每天 ≥2 指标全是拍的，没有一条真实蜕皮序列可验证。等 Phase 2 采到数据后回头调参，这是项目当前最大的技术风险
- [ ] 蒙白数据从哪来 —— 公开数据里一张蒙白图都没有，现在只能跑二态。2026-11-09 全网搜索（`docs/data-search-2026-11-09.md`）从 B 站/搜狗图片/iNaturalist 收了 417 张候选图，可能有零星蒙白，但量级远不够训练。产品真正值钱的是蒙白预警（皮还完整、加湿还来得及），而「正在蜕皮」已经晚了。只能靠自采
- [ ] 个体校准（个性化模型）要不要做 —— 用户方向（m07232）：**不要求用户拍几十张**，而是靠饲养箱摄像头每 30 分钟自动抓拍、持续累积该个体的样本，用户只在必要时少量补拍。技术依据：CLIP 特征 + 每类 20 张原型分类器已到 0.834 准确率 / 0.90 蜕皮召回（见 `docs/spike-zeroshot.md`）。等真机跑起来、有真实累积样本后再决定是否写进正式规格（会牵动 App 设置流程与隐私设计）
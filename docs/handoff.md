# 交接文档

> 这份文档给「新会话」或「接手的人」看：项目现在在哪、做过什么决定、下一步做什么。
> 读完这一份，就能接着干，不用翻旧对话。
> 操作规范与代码标准见 `AGENTS.md`，本文只记录项目状态与决策。

## 项目一句话

shedguard：给爬宠主人的蜕皮预警设备。一个夹在饲养箱玻璃上的摄像头，AI 每天固定机位拍一张，识别守宫处于哪个蜕皮阶段（正常 / 蒙白 / 蜕皮中），在需要加湿的时候告诉主人「它要蜕了，现在该做什么」。第一版先做状态识别；「提前几天预测」要等个体周期基线积累出来再做。

## 当前阶段

**Phase 1 完成（M1 骨架 → M2 图片接入 → M3 时序输入层 → M5 信号层 → M4 定位模型 → M6 判定层 → M7 蜕皮状态识别）—— 后端能收图、去重、归档、按天查询、收敛成序列、记录蜕皮事件、对单帧算出体表指标、按时序算出「今天是否异常」，还能对每张图判定「正常 / 蒙白 / 蜕皮中」并推导蜕皮事件；两个模型都已训练并在服务端跑通。下一步是真实数据采集（Phase 2）。**

公开数据调研已完成（见 `docs/data-survey.md`），结论是全世界都不存在「守宫蜕皮时序」数据集，自采是唯一路径。Roboflow 的 `capstone-habql/gecko_1`（1,163 张，Public Domain）已下载到 `data/raw/gecko1/`。它**能**训「守宫在哪」与「皮是否正在掉」，但**不能**训「蒙白」——标注里的蜕皮样本全是皮已掀起的瞬间，没有一张静止蒙白态；而且分辨率与类别强耦合（短边 < 400px 占 90.9%，蜕皮样本几乎全在高清微距图上），直接做三分类会退化成「白背景 + 高清 = 蜕皮」的捷径学习，所以拆成检测器与状态分类器两个模型分别训。

2026-11-09 又做了一轮全网搜索（见 `docs/data-search-2026-11-09.md`）：确认 Kaggle、GitHub、HuggingFace、Zenodo、iNaturalist 上都不存在蜕皮状态标注数据集；从 B 站蜕皮视频（抽帧）、搜狗图片、iNaturalist 收集到 417 张新图片存 `data/collected/`（不入库），全部可见光、无蒙白标注，作为候选池待人工筛选后扩充训练集。蒙白与红外数据依然为零，自采仍是唯一路径。

后端现状（`server/`）：配置校验（21 个 `SHEDGUARD_*` 项）、结构化 JSON 日志与 `request_id` 贯穿、统一错误契约、`/healthz` 与 `/readyz`、`POST /api/v1/images`（multipart 或裸 body、SHA-256 幂等）、`GET /api/v1/images`（按天分页）、取原图与元数据、`GET /api/v1/series`（每日代表帧与缺失日）、`PUT/GET /api/v1/shed-events`、`POST /api/v1/analysis/{image_id}`（六项体表指标 + 曝光归一化）、`GET /api/v1/series/{device_id}/signals`（稳健 Z 分数与四状态判定）、`POST /api/v1/shedding/{image_id}`（蜕皮状态识别）、`GET /api/v1/series/{device_id}/shedding`（逐日状态与事件推导）、Alembic 四次迁移在启动时自动升级、CI 与 pre-commit。263 个测试，覆盖率 96.5%，ruff 与 mypy strict 全绿。

定位模型（`ml/`）：`yolov8n` 微调 50 轮（RTX 5070 上 3.6 分钟），单类别 `gecko`，测试集 `mAP50 = 0.902 / mAP50-95 = 0.578`，通过 0.85 验收线。导出 `ml/models/gecko-det.onnx`（12.2 MB，不进仓库），已用服务端 `OnnxDetector` 加载真实网图验证，8/8 检出。已知短板：训练集全是可见光，一张红外图都没有。

状态分类器（`ml/`）：`resnet18` 微调 15 轮（约 2 分钟），任务是给检测框裁出的守宫判定蜕皮阶段。**当前只有二态**（`normal` / `shedding`），因为公开数据里蒙白样本是零。测试集准确率 0.911，`shedding` 召回 0.781。导出 `ml/models/gecko-state.onnx`（44.8 MB）+ `.labels.json`，服务端从 `labels.json` 读类别顺序，所以将来换成三态模型只需换文件、不改代码。真机冒烟：8 张图 7 张判对，1 张置信度 0.513 被降级为 `unknown`。

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
│   ├── roadmap.md            # 项目路线图（分阶段规划与验收标准）
│   └── specs/
│       ├── 2026-11-02-server-image-ingest-design.md   # 后端图片接入服务设计规格
│       ├── 2026-11-02-series-and-events-design.md     # 每日序列与蜕皮事件设计规格
│       ├── 2026-11-02-shed-detection-core-design.md   # 蜕皮识别三层架构（定位/信号/时序）
│       ├── 2026-11-02-shed-judgement-design.md        # 时序判定层（稳健 Z 分数与告警状态机）
│       └── 2026-11-04-shedding-state-design.md        # 蜕皮状态识别（四态、事件推导、分类器接入）
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
├── firmware/README.md        # ESP32-S3-EYE 固件占位
├── server/                   # 后端服务（图片接入与分析已完成）
│   ├── README.md             # 运行、接口、配置与开发说明
│   ├── pyproject.toml        # 依赖、ruff、mypy、pytest、覆盖率配置
│   ├── alembic.ini           # 迁移配置
│   ├── requirements.lock     # 完整依赖锁定
│   ├── .env.example          # 配置样例
│   ├── src/shedguard_server/ # api、domain、services、infra、migrations
│   └── tests/                # unit 与 integration
└── app/README.md             # 前端占位
```

## 下一步（按顺序）

分阶段计划、依赖关系与验收标准见 `docs/roadmap.md`，这里只列最近几步：

1. ~~后端图片接收服务（Phase 0–1）~~ —— 已完成：M1 骨架、M2 图片接入、M3 每日序列与蜕皮事件、M5 信号层
2. ~~M4 定位模型训练~~ —— 已完成：测试集 mAP50 0.902，ONNX 已接入服务端并验证
3. ~~M6 时序判定层~~ —— 已完成：`GET /api/v1/series/{device_id}/signals`，稳健 Z 分数 + 四状态机
4. ~~M7 蜕皮状态识别~~ —— 已完成：检测 → 裁剪 → 分类，二态模型（`normal` / `shedding`）准确率 0.911，服务端四层打通
5. ~~导出 Roboflow `capstone-habql/gecko_1`~~ —— 已完成，落在 `data/raw/gecko1/`
6. **数据流提前启动（Phase 2）** —— 不等固件，先用手机临时机位开始积累影像。这是判断层与状态分类器能否被验证的唯一路径
6a. **人工复核 `data/collected/` 的 417 张新图** —— 剔除误检与不相关图片，按 normal / shedding / 疑似蒙白 手动标注，然后并入 `ml/datasets/gecko-state/` 重训分类器（见 `docs/data-search-2026-11-09.md`）
7. **补蒙白样本** —— 现有公开数据里蒙白图是零，三态跑不起来。这一项和数据流是同一件事的两面：自采时每天固定拍，蒙白那 1–2 天自然会被拍到
8. 固件跑通（Phase 3）：拍照 → WiFi 上传 → 服务端收到图（上传协议已就绪）
9. ~~知识库核实（Phase 9）~~ —— 第一轮已完成：全部条目换成带来源的值，修正 8 处错误（最要紧的是「需要 UVB」「日常湿度 30–40%」「蜕皮频率无一致来源」）。剩余 5 项需真实个体数据

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

## 待确认

- [x] ~~是否先买一只豹纹守宫~~ —— 已定：不买，先用公开数据与手机自采起步
- [x] ~~后端规格的三个技术决策~~ —— 已定：FastAPI + SQLAlchemy + Alembic、`/api/v1`、默认监听 `127.0.0.1`
- [x] ~~开发阶段先做固件还是先做后端图像分析~~ —— 已定：先后端接收端点
- [x] ~~是否注册 Roboflow 账号导出 `capstone-habql/gecko_1`~~ —— 已定：已导出并评估，只用作定位训练集
- [ ] 判定层的阈值怎么校准 —— 当前 `z ≥ 2.0`、连续 2 天、每天 ≥2 指标全是拍的，没有一条真实蜕皮序列可验证。等 Phase 2 采到数据后回头调参，这是项目当前最大的技术风险
- [ ] 蒙白数据从哪来 —— 公开数据里一张蒙白图都没有，现在只能跑二态。2026-11-09 全网搜索（`docs/data-search-2026-11-09.md`）从 B 站/搜狗图片/iNaturalist 收了 417 张候选图，可能有零星蒙白，但量级远不够训练。产品真正值钱的是蒙白预警（皮还完整、加湿还来得及），而「正在蜕皮」已经晚了。只能靠自采
- [ ] 数据自采的机位与频次（手机临时机位方案，见 `docs/roadmap.md` Phase 2）
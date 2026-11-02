# 交接文档

> 这份文档给「新会话」或「接手的人」看：项目现在在哪、做过什么决定、下一步做什么。
> 读完这一份，就能接着干，不用翻旧对话。
> 操作规范与代码标准见 `AGENTS.md`，本文只记录项目状态与决策。

## 项目一句话

shedguard：给爬宠主人的蜕皮预警设备。一个夹在饲养箱玻璃上的摄像头，AI 识别蜕皮前兆，提前告诉主人「它要蜕了，现在该做什么」。

## 当前阶段

**Phase 1 完成（M1 骨架 → M2 图片接入 → M3 时序输入层 → M5 信号层）—— 后端已能收图、去重、归档、按天查询、收敛成序列、记录蜕皮事件，并对单帧算出体表指标；下一步是 M4 训练定位模型，再进 M6 时序判定。**

公开数据调研已完成（见 `docs/data-survey.md`），结论是全世界都不存在「守宫蜕皮时序」数据集，自采是唯一路径。Roboflow 的 `capstone-habql/gecko_1`（1,163 张，Public Domain）已下载到 `data/raw/gecko1/`，评估结论是**只能用来训「守宫在哪」，不能用来训「是否蜕皮」**：短边 < 400px 占 90.9%，分辨率与类别强耦合，直接做三分类会退化成「白背景 + 高清 = 蜕皮」的捷径学习。

后端现状（`server/`）：配置校验（13 个 `SHEDGUARD_*` 项）、结构化 JSON 日志与 `request_id` 贯穿、统一错误契约、`/healthz` 与 `/readyz`、`POST /api/v1/images`（multipart 或裸 body、SHA-256 幂等）、`GET /api/v1/images`（按天分页）、取原图与元数据、`GET /api/v1/series`（每日代表帧与缺失日）、`PUT/GET /api/v1/shed-events`、`POST /api/v1/analysis/{image_id}`（六项体表指标 + 曝光归一化）、Alembic 三次迁移在启动时自动升级、CI 与 pre-commit。177 个测试，覆盖率 95.8%，ruff 与 mypy strict 全绿。

## 已经定下来的决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 产品切口 | 蜕皮识别 | 卡皮会导致趾头/尾巴坏死甚至死亡；现有产品只解决环境稳定 |
| 不做 | 自动喂食、控温湿、整箱产品、诊断 | 喂食是玩家唯一乐趣；整箱要打供应链价格战 |
| 硬件 | ESP32-S3-EYE + 红外补光 + 支架 | 已有板子；守宫夜行，OV2640 夜拍全黑，必须红外 |
| 形态 | 外挂（夹在玻璃上），不做整箱 | 成本低，不改变用户现有饲养方式 |
| 核心算法 | 固定机位 + 每日对比 + 时序判断 | 不做单张照片识别（不可靠） |
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
│   ├── gecko-params.md       # 豹纹守宫参数模板（含 [待核实] 项）
│   ├── shed-detection.md     # 蜕皮识别思路与验证方法
│   ├── data-survey.md        # 公开数据可获得性调研（结论：必须自采）
│   ├── handoff.md            # 本文件
│   ├── roadmap.md            # 项目路线图（分阶段规划与验收标准）
│   └── specs/
│       ├── 2026-11-02-server-image-ingest-design.md   # 后端图片接入服务设计规格
│       ├── 2026-11-02-series-and-events-design.md     # 每日序列与蜕皮事件设计规格
│       └── 2026-11-02-shed-detection-core-design.md   # 蜕皮识别三层架构（定位/信号/时序）
├── .github/workflows/ci.yml  # GitHub Actions：ruff + mypy + 覆盖率
├── .pre-commit-config.yaml   # 本地提交前钩子
├── data/
│   └── raw/gecko1/           # Roboflow gecko_1 原始数据（1,163 张，不入库）
├── ml/
│   ├── prepare_detection_dataset.py  # 分割标注 → 检测框，构建单类别数据集
│   └── datasets/gecko-det/           # 转换产物（1,120 图 / 1,124 框，不入库）
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
2. M4 定位模型训练：`ml/datasets/gecko-det/` 已构建（1,120 图 / 1,124 框），装 torch + ultralytics 后训 YOLOv8n 单类别，导出 ONNX 供 `SHEDGUARD_DETECTOR_MODEL` 加载
3. M6 时序判定层：用指标序列做稳健 Z 分数，定义告警规则与趋势端点
4. ~~导出 Roboflow `capstone-habql/gecko_1`~~ —— 已完成，落在 `data/raw/gecko1/`
5. 数据流提前启动（Phase 2）：不等固件，先用手机临时机位开始积累影像
6. 固件跑通（Phase 3）：拍照 → WiFi 上传 → 服务端收到图（上传协议已就绪）
7. 知识库核实（Phase 9）：填完 `docs/gecko-params.md` 的 `[待核实]` 项，可与其他步骤并行

> 为什么先后端：固件的上传目标必须先存在。否则板子写完了也没有真实端点可发，联调只能对着假想端点做，问题会一直拖到集成时才暴露。

## 环境注意

- 这台机器的 Git 自带 `sh.exe` 在沙箱里起不来，推送前需要先跑：
  ```powershell
  $env:GIT_SSH = "C:/windows/System32/OpenSSH/ssh.exe"
  $env:GIT_SSH_VARIANT = "ssh"
  ```
- 远端：`git@github.com:linzizhen/shedguard.git`
- 本机没有可用的全局 `python` 命令（只有 Microsoft Store 占位别名），执行 Python 相关命令需显式指定解释器。

## 待确认

- [x] ~~是否先买一只豹纹守宫~~ —— 已定：不买，先用公开数据与手机自采起步
- [x] ~~后端规格的三个技术决策~~ —— 已定：FastAPI + SQLAlchemy + Alembic、`/api/v1`、默认监听 `127.0.0.1`
- [x] ~~开发阶段先做固件还是先做后端图像分析~~ —— 已定：先后端接收端点
- [x] ~~是否注册 Roboflow 账号导出 `capstone-habql/gecko_1`~~ —— 已定：已导出并评估，只用作定位训练集
- [ ] 数据自采的机位与频次（手机临时机位方案，见 `docs/roadmap.md` Phase 2）
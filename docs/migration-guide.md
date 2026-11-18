# 换一台电脑继续开发：迁移方案

> 目标：在新机器上从零恢复到「能改代码、能跑测试、能起服务、能看 App」的状态。
> 适用范围：Windows → Windows（含另一台 Windows）。跨平台差异见 §8。

---

## 0. 先看清什么在 Git 里、什么不在

仓库已跟踪 **270 个文件**，`.git` 只有 **1.7 MB**。但项目能跑起来还依赖一批**故意不入库**的东西：

| 内容 | 大小 | 在 Git 里？ | 新机器怎么办 |
|---|---|---|---|
| 全部源码、文档、配置样例、CI、脚本 | — | ✅ 是 | `git clone` 即可 |
| `ml/models/*.onnx` | 195 MB（实际只需 2 个 ≈ 55 MB） | ❌ 忽略 | **必须手动拷**，或重新训练 |
| `ml/datasets/*` | 194 MB | ❌ 忽略 | 可从 `data/raw` 重建（推荐）或直接拷 |
| `data/raw/gecko1`（原始公开数据集） | 26 MB | ❌ 忽略 | **必须拷**，是重建一切数据集的源头 |
| `data/collected`、`data/collected_crops` | 100 + 102 MB | ❌ 忽略 | 拷（想复现 v2）或重跑抓取脚本 |
| `.venv/` | **3.9 GB** | ❌ 忽略 | **绝对不要拷**，重建（见 §3 原因） |
| `app/node_modules/` | 414 MB | ❌ 忽略 | 重建：`npm ci` |
| `firmware/build/`、`managed_components/` | 151 MB | ❌ 忽略 | 重建：`idf.py build` |
| `.tmp/` | 3.4 GB | ❌ 忽略 | **丢弃**，但见 §5 的密钥例外 |
| `server/.env` | — | ❌ 忽略（本机也没有，用的是 `.env.example`） | 按需新建 |

**结论：需要跨机器搬运的只有约 285 MB**（两个模型 55 MB + `data/` 230 MB）。其余全部可重建。

---

## 1. 方案 A（推荐）：Git + 移动硬盘拷数据

### 1.1 新机器装基础环境

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Git | 任意较新版本 | 需要能走 SSH |
| Python | **≥ 3.12**（本机是 3.14.6） | 从 python.org 装，勾选 Add to PATH |
| Node.js | **≥ 20**（本机是 v24.21.0） | 装 LTS 即可 |
| ESP-IDF | **v5.4.4** | 只在要编固件时装；官方 installer 或离线包 |

### 1.2 配 Git 身份与 SSH

```powershell
git config --global user.name "linzizhen"
git config --global user.email "3541404414@qq.com"

# 生成密钥（已有可跳过，把旧机器的 ~/.ssh 拷过来更省事）
ssh-keygen -t ed25519 -C "3541404414@qq.com"
# 把 ~/.ssh/id_ed25519.pub 的内容贴到 GitHub → Settings → SSH and GPG keys
ssh -T git@github.com   # 出现 "Hi linzizhen!" 即成功
```

> 本机踩过的坑：在受限沙箱里 `git push` 会报 `couldn't create signal pipe, Win32 error 5`，需要设置
> `$env:GIT_SSH="C:/Windows/System32/OpenSSH/ssh.exe"`。新机器如果用普通终端通常不需要这一步。

### 1.3 克隆并切到正确的分支

```powershell
git clone git@github.com:linzizhen/shedguard.git D:\shedguard
cd D:\shedguard
git checkout develop        # develop 是集成线，日常在这里
git log --oneline -3        # 确认能看到最新提交
git tag                     # 应看到 v0.1.0
```

> **分支模型**：`main` 只放已发布版本（当前停在 `v0.1.0`），日常提交进 `develop`，
> 单个功能走 `feature/*` 再合并回 `develop`。详见 `docs/git-flow.md`。

### 1.4 从旧机器拷数据（约 285 MB）

在**旧机器**上执行，把下面四样拷到 U 盘或网络位置：

```powershell
# 1) 模型（只需两个；v1/v3/smoke 是历史产物，可不带）
ml\models\gecko-det.onnx          # 12.2 MB  守宫检测器
ml\models\gecko-state-v2.onnx     # 42.7 MB  蜕皮状态分类器（线上用这个）
ml\models\gecko-state-v2.labels.json

# 2) 原始数据集（重建所有派生数据集的源头）
data\raw\                          # 26 MB

# 3) 采集数据（想复现 v2 训练集才需要，否则可省）
data\collected_crops\              # 102 MB（含 manifest.csv / review.csv，这两个 CSV 很重要）
data\collected\                    # 100 MB（网页原图，可省）

# 4) 摄像头凭据的解密密钥（见 §5）
.tmp\p30_key.txt                   # 44 字节
```

拷到**新机器**的同一相对路径下（`D:\shedguard\ml\models\`、`D:\shedguard\data\`、`D:\shedguard\.tmp\`）。

### 1.5 建 Python 虚拟环境并装依赖

```powershell
cd D:\shedguard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# 服务端（含测试工具）
.\.venv\Scripts\python.exe -m pip install -e "server[dev]"

# 训练侧（只有要训模型才装，约 3 GB：torch + ultralytics + onnx）
.\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
```

> **不要用 `server/requirements.lock`**：它是从本机 Python 3.14 freeze 出来的，里面
> `numpy==2.5.4` 这类版本在公开 PyPI 上不存在（P19 已查明）。CI 与安装一律以
> `server/pyproject.toml` 的区间为准。

### 1.6 装 App 依赖

```powershell
cd D:\shedguard\app
npm ci                     # 严格按 package-lock.json 装（比 npm install 稳）
npx expo start             # 起开发服务；按 w 开网页版，按扫码连真机
```

### 1.7 验证：跑质量门

```powershell
# 服务端
cd D:\shedguard\server
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m mypy src tests
..\.venv\Scripts\python.exe -m pytest --junitxml=..\.tmp\junit.xml
# 期望：ruff 全绿、mypy Success、pytest 520 passed / 0 failed

# App
cd D:\shedguard\app
npx tsc --noEmit
npx eslint .
```

> `pytest -q` 的最终统计行在 PowerShell 管道里会丢，用 `--junitxml` 读结果更可靠。

### 1.8 起服务看真东西

```powershell
cd D:\shedguard
$env:PYTHONPATH = "D:\shedguard\server\src"
$env:SHEDGUARD_DATA_DIR = "D:\shedguard\data"
$env:SHEDGUARD_DETECTOR_MODEL = "D:\shedguard\ml\models\gecko-det.onnx"
$env:SHEDGUARD_STATE_MODEL = "D:\shedguard\ml\models\gecko-state-v2.onnx"
.\.venv\Scripts\python.exe -m shedguard_server
# 另开一个窗口：curl http://127.0.0.1:8000/healthz  →  {"status":"ok"}
```

---

## 2. 方案 B：只带代码，全部重建

适合新机器能联网、且不急着复现历史训练结果的情况。

```powershell
git clone git@github.com:linzizhen/shedguard.git D:\shedguard
# 环境同 §1.1–1.3、§1.5–1.6

# 数据只能自己重新搞：data/raw 是 Roboflow 公开数据集，需要按 ml/README.md 里的来源重新下载
# 没有 data/raw 就重建不了数据集；没有数据集就训不出模型
```

**代价**：
- 两个 `.onnx` 模型必须重新训练（检测器 50 epoch、分类器 15 epoch，本机 RTX 5070 上分别约 20 分钟 / 2 分钟）
- 检测器训练依赖 Roboflow 数据集，若该数据集已下线则**无法复现**
- `data/collected_crops/review.csv` 是人工逐簇复核的成果（325 簇判定），丢了只能重做

**建议**：至少把 `data/raw`（26 MB）和 `data/collected_crops` 里的两个 CSV 带上，这是最不可替代的部分。

---

## 3. 为什么 `.venv` 绝对不能拷

`.venv/pyvenv.cfg` 里写死了绝对路径：

```
home = C:\Users\user\anaconda3
command = C:\Users\user\anaconda3\python.exe -m venv D:\shedguard\.venv
```

拷到新机器后，`Scripts\python.exe` 仍指向旧机器的解释器路径，轻则报找不到解释器，重则用了错误的 Python 版本。**3.9 GB 换来一堆诡异错误，不值得。** `node_modules` 同理（含平台相关的二进制），一律重建。

---

## 4. 必须记住的环境差异（本机踩过的坑）

| 现象 | 原因 | 新机器怎么办 |
|---|---|---|
| `python` 命令指向 Microsoft Store 占位符 | 本机没装全局 Python，只有 Anaconda | 装 python.org 版本并勾选 PATH，或始终用 `.venv\Scripts\python.exe` |
| `pip install` 报 `Permission denied ... pip-unpack-*.whl.metadata` | 沙箱拒绝写临时目录 | 设 `$env:TEMP="D:\shedguard\.tmp\piptmp"`，或用完整权限终端 |
| `npx` / `npm.ps1` 被执行策略挡 | PowerShell 执行策略 | 用 `npx.cmd`，或 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `expo start` 报写 `C:\Users\user\.expo` 失败 | 沙箱 | 普通终端不受影响；受限环境需提权 |
| 含中文的 `.ps1` 报 `Unexpected token` | 文件存成了无 BOM 的 UTF-8，PowerShell 5.1 按 GBK 解码 | 用 UTF-8 **带 BOM** 保存（`scripts/gitflow.ps1` 已处理） |
| `.cmd` 里写中文注释报 `'...' is not recognized` | cmd.exe 按 ANSI 解析 | `.cmd` 只写 ASCII，中文放进 `.ps1` |
| 改中文源文件后满屏乱码 | `Get-Content -Raw` + `Set-Content` 会按 GBK 解码 UTF-8 | **绝不用管道批量改含中文的文件**，用编辑器或 `git checkout --` 恢复 |

---

## 5. 密钥与敏感数据清单

| 东西 | 位置 | 丢了会怎样 |
|---|---|---|
| **Fernet 密钥**（解密摄像头密码） | `.tmp\p30_key.txt` | 数据库里存的摄像头密码解不开，用户需重新填一次密码。**密钥本身别进 Git** |
| GitHub SSH 私钥 | `~/.ssh/id_ed25519` | 需要重新生成并加回 GitHub |
| HuggingFace fine-grained token（数据贡献收件箱） | 只在运行时环境变量里，不入库 | 重新在 HF 网站生成，见 `docs/contribution-setup.md` |
| Expo / EAS 登录态 | `~/.expo/` | `eas login` 重新登 |
| 服务端配置 | `server/.env`（本机**没有**，全部用环境变量） | 按 `server/.env.example` 的 86 行按需建 |

> **不要**把这个密钥放进 Git 或任何同步盘。它只用来解密「用户自己家的摄像头密码」，
> 迁移时用 U 盘或密码管理器单独带过去。

---

## 6. 迁移后的第一次提交（验证链路通）

```powershell
cd D:\shedguard
git checkout -b feature/smoke-migration   # 或直接用 scripts/gitflow.cmd feature-start -Name smoke-migration
# 随便改一行文档
git add -A
git commit -m "chore: 验证新机器的提交与推送链路"
git push -u origin feature/smoke-migration
```

能推上去，说明 SSH、身份、远端都对。然后 `scripts/gitflow.cmd feature-finish -Name smoke-migration` 收尾。

---

## 7. 可选：把「不可重建」的东西也纳入版本管理

目前模型与数据都在 `.gitignore` 里，靠人工搬运。如果以后想彻底避免「换机器就丢」：

| 做法 | 适合 | 代价 |
|---|---|---|
| Git LFS 存 `ml/models/*.onnx` | 模型不大、更新不频繁 | 仓库变大；GitHub 免费额度 1 GB 存储 / 1 GB 月流量 |
| HuggingFace 私有 dataset 仓库存模型与数据集 | 已在用（数据贡献收件箱） | 需要 token；多一层外部依赖 |
| 云盘（OneDrive/坚果云）同步 `data/` 与 `ml/models/` | 个人开发 | 同步冲突；大文件慢 |
| 保持现状 + 本文档 | 单人开发 | 每次换机手动搬 285 MB |

**当前建议**：保持现状。285 MB 的搬运量不值得引入 LFS 或外部存储的复杂度。

---

## 8. 如果新机器是 macOS / Linux

| 项 | 变化 |
|---|---|
| 路径 | `D:\shedguard` → `~/shedguard`，所有文档里的绝对路径都要改 |
| 虚拟环境 | `python3 -m venv .venv`，激活是 `source .venv/bin/activate`，可执行文件在 `.venv/bin/python` |
| 固件 | ESP-IDF 支持 macOS/Linux，但 `firmware/main/*.c` 里的 `app_config.h` 用 `#ifndef` 宏，无需改 |
| 服务端 | 纯 Python + SQLite + ONNX Runtime，跨平台无碍 |
| App | Expo 支持 macOS（iOS 真机需要 Mac）；Windows 上只能 Android |
| 脚本 | `scripts/gitflow.ps1` 是 PowerShell，Linux 需要改写或用等价 git 命令（`docs/git-flow.md` 里有纯 git 版本） |
| 换行符 | 建议 `git config core.autocrlf input`，避免整仓 CRLF/LF 抖动 |

---

## 9. 一页速查

```powershell
# 新机器完整流程（假设数据已拷到 D:\shedguard）
git clone git@github.com:linzizhen/shedguard.git D:\shedguard
cd D:\shedguard; git checkout develop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "server[dev]"
cd server; ..\.venv\Scripts\python.exe -m pytest --junitxml=..\.tmp\junit.xml
cd ..\app; npm ci; npx tsc --noEmit; npx eslint .
cd ..; git config user.name "linzizhen"; git config user.email "3541404414@qq.com"
```

跑通 `pytest` 与 `tsc`，就说明这台机器已经能继续开发了。

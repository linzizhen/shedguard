# Git Flow 分支规范

> 2026-11-13 起，项目用 git flow 管理分支。本文件是分支与发布的操作手册；计划层面的约束见 `docs/plan.md` §0。

## 1. 为什么用它

- 主线功能（蜕皮检测、萌照）需要能**随时回滚到「上次能演示的版本」**，而不是只能往前滚。
- 固件、App、服务端会并行推进，短期分支让「半成品」不污染主线。
- 发布过的版本要有明确标签，方便对照「线上跑的是哪一版」。

## 2. 分支模型

| 分支 | 生命周期 | 从哪来 | 合到哪 | 用途 |
|---|---|---|---|---|
| `main` | 长期 | — | — | 可发布版本。只接受 `release/*` 与 `hotfix/*` 的合并 |
| `develop` | 长期 | `main` | — | 集成线。功能都先合到这里，跑通再发版 |
| `feature/<name>` | 短期 | `develop` | `develop` | 单个功能或单条加固项 |
| `release/<x.y.z>` | 短期 | `develop` | `main` + `develop` | 只改版本号、文档、本次发布的修复 |
| `hotfix/<x.y.z>` | 短期 | `main` | `main` + `develop` | 线上问题，最小改动 |

约定：

- 分支名用小写字母、数字、短横线：`feature/portrait-album-paging`、`release/0.2.0`、`hotfix/0.1.1`。
- **合并一律 `--no-ff`**，保留分支痕迹，方便看出「这次改动是一个整体」。
- 合并回 `develop` 后删掉短期分支；远端同步删。
- 标签 `v<版本号>` 打在 `main` 上，与 `release-finish` 同时产生。

## 3. 版本号

语义化三段式 `<major>.<minor>.<patch>`，当前基线 **v0.1.0**（蜕皮检测链路 + App + 萌照，未上板、未真机验证）：

- `patch`：修 bug、改配置默认值、文案；
- `minor`：新增功能（例如蒙白三态、环境控制）；
- `major`：协议或数据不兼容（迁移无法自动回退、接口破坏性变更）。

发版时同步改两处版本号：`app/app.json` 的 `expo.version`、`server/pyproject.toml` 的 `version`。

## 4. 日常流程

> 助手有两个入口：`.\scripts\gitflow.cmd`（推荐，内部用 `powershell -ExecutionPolicy Bypass` 调 `.ps1`，本机没有 `pwsh` 也能用）与 `scripts\gitflow.ps1`（在装了 PowerShell 7 的机器上可直接 `pwsh` 执行）。参数完全一样。

### 4.1 开一个功能

```powershell
.\scripts\gitflow.cmd feature-start -Name portrait-album-paging
# 写代码、跑质量门、提交（可多次提交，一条一件事）
.\scripts\gitflow.cmd feature-finish -Name portrait-album-paging
```

`feature-finish` 会：切回 `develop` → `pull --ff-only` → `merge --no-ff` → 删除本地分支 → 推送 `develop`。

### 4.2 不装助手也能做（纯 git）

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c feature/portrait-album-paging
# ……开发与提交……
git switch develop
git pull --ff-only origin develop
git merge --no-ff feature/portrait-album-paging -m "merge: feature/portrait-album-paging"
git branch -d feature/portrait-album-paging
git push origin develop
```

### 4.3 发版

```powershell
.\scripts\gitflow.cmd release-start -Version 0.2.0
# 改 app/app.json 与 server/pyproject.toml 的版本号，补 handoff/plan 状态
.\scripts\gitflow.cmd release-finish -Version 0.2.0
```

`release-finish` 会：合并到 `main` → 打 `v0.2.0` 标签 → 再合回 `develop` → 推送两条长期分支与标签。

### 4.4 线上热修

```powershell
.\scripts\gitflow.cmd hotfix-start -Version 0.1.1
# 最小修复 + 回归测试
.\scripts\gitflow.cmd hotfix-finish -Version 0.1.1
```

热修必须同时回灌 `develop`，否则下次发版会把 bug 带回来。

## 5. 质量门（合并前必须全绿）

服务端（在 `server/` 下）：

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src tests
.\.venv\Scripts\python.exe -m pytest --junitxml=..\.tmp\junit.xml
```

App（在 `app/` 下）：`npx.cmd tsc --noEmit`、`npx.cmd eslint .`。

CI 在 `push` 到 `main` / `develop` 以及任何 PR 时跑服务端的 ruff / mypy / pytest，覆盖率低于 85% 直接失败。

## 6. 远端保护（需要在 GitHub 网页上手动设一次）

本机没有 `gh` CLI，以下由仓库管理员在 GitHub 设置：

1. **默认分支**建议保持 `main`（对外展示用），日常开发在 `develop`。
2. 给 `main` 开保护：禁止直接 push、要求 PR、要求 CI 通过。
3. 给 `develop` 开保护：要求 CI 通过；是否要求 PR 视协作人数而定（单人可只靠 CI）。
4. 合并方式只保留 **Merge commit**（与 `--no-ff` 一致），关掉 squash 与 rebase merge，避免丢失分支结构。

## 7. 和本项目其他约定的关系

- **数据与模型不入库**：`data/`、`ml/datasets/`、`ml/models/` 都在 `.gitignore` 里，分支切换不会带走它们；换分支后跑训练要重新确认 `ml/models/` 是否还在。
- **计划和规格先于代码**：新方案仍然先改 `docs/plan.md`，再在 `feature/*` 上写规格与实现，合并顺序不变。
- **提交格式不变**：`<type>(<scope>): <中文简述>`，原子提交；一个 feature 分支里允许多个原子提交。
- **`.tmp/` 是本地临时区**，被忽略，不要在里面放需要跨机器复现的东西。
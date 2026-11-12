# 踩坑与防复发清单（lessons.md）

> 这份文件只记**已经真实犯过的错**，不写假设性的注意事项。
> 用法：每次动手前扫一眼对应小节；犯错后**立刻**把新条目补进来（现象 → 根因 → 正确做法 → 自查），否则下次还会踩。
> 新条目追加到对应分类末尾，不要重排已有编号。

---

## 0. 开工前 30 秒自查（最高频的五条）

1. 要改的文件里有中文吗？→ **只用 `edit` / `write` 工具**，禁止 `Get-Content -Raw` + `Set-Content` 管道。
2. 要新建测试文件吗？→ 文件名在 `tests/` 全树**唯一**（`unit/` 与 `integration/` 也算同一命名空间）。
3. 跑 `pytest` 要看统计吗？→ 加 `--junitxml`，不要读 `-q` 的尾行。
4. 跑 `mypy` 吗？→ 只跑 `mypy src tests`，不要 `mypy .`。
5. 调 `npx` / `npm` / Chrome / git push / pip 吗？→ 先想清楚是否需要 `danger-full-access`，以及是否必须用 `.cmd` 后缀。

---

## 1. 文件与文本编码（踩过 2 次，代价最高）

### 1.1 PowerShell 管道改写 UTF-8 中文文件 → 全文乱码

- **现象**：`classifier.py` 全部中文变 `锛?`；`docs/handoff.md` 与 `docs/plan.md` 出现「椤圭洰鎬昏鍒掞紙鍞竴鏉冨▉锛?」，diff 一片红。
- **根因**：`Get-Content -Raw` 在中文 Windows 上按 GBK 解码 UTF-8 字节，`Set-Content -Encoding utf8` 再把错误字符写回，不可逆。
- **正确做法**：改含中文的文件，一律 `edit`（定点替换）或 `write`（整文件重写）。
- **批量改名**：用 Python 脚本读 `encoding="utf-8"` + `re.sub` + 写回，不要用 PowerShell 管道。
- **自查**：`git diff` 里若出现成片非中文乱码，立即 `git checkout -- <file>` 回滚，换工具重做。

### 1.2 控制台中文乱码 ≠ 文件坏了

- **现象**：`read` 正常但 PowerShell 输出是乱码，误判文件损坏。
- **正确做法**：显示层问题用 `$env:PYTHONIOENCODING="utf-8"` + `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8`；判断文件是否损坏只看 `git diff` 与 `read` 工具。

---

## 2. 测试（踩过 4 次）

### 2.1 同名测试文件 → pytest `import file mismatch`

- **现象**：`imported module 'test_shedding' has this __file__ attribute: ...`。
- **根因**：`tests/unit/test_x.py` 与 `tests/integration/test_x.py` 在 pytest 的模块命名空间里冲突。
- **已发生的四次**：`test_shedding.py` → `test_shedding_domain.py`；`test_alerts.py` → `test_alerts_api.py`；`test_health.py` → `test_health_domain.py`；`test_health_api.py` → `test_health_alerts_api.py`。
- **正确做法**：新建测试文件前先 `glob tests/**/test_*.py` 查重；命名带层次后缀（`_domain` / `_api` / `_service`）。

### 2.2 `pytest -q` 统计行在 PowerShell 管道里丢失

- **正确做法**：`pytest --junitxml=D:\shedguard\.tmp\junit.xml`，再读 XML 的 `testsuite` 属性拿 tests/failures/errors。

### 2.3 沙箱下 `tmp_path` 触发 `PermissionError`

- **现象**：集成测试用 `tmp_path` 建目录失败。
- **正确做法**：统一用 `tests/integration/conftest.py` 的 `workdir` fixture。

### 2.4 改完代码没重跑全量就下结论

- **正确做法**：任何服务端改动，收尾必须跑一次 `pytest --junitxml` + `ruff check .` + `mypy src tests` 三件套，缺一不算完成。

---

## 3. 类型检查与 Lint（踩过 3 次）

### 3.1 `mypy .` 撞 pytest 缓存目录

- **现象**：`PermissionError` 或扫到 `.pytest_cache`。
- **正确做法**：`mypy src tests`（`pyproject.toml` 的 `files=["src","tests"]` 已固定）。

### 3.2 `client.app.state.x = ...` 报 attr-defined

- **正确做法**：行尾加 `# type: ignore[attr-defined]`。**不要**用 PowerShell 管道批量插注释——曾把注释插到赋值语句中间，改成 Python 正则重做。

### 3.3 `Settings(_env_file=None, **base)` 的 ignore 码写错

- **正确做法**：`# type: ignore[call-arg]`（不是 `arg-type`）。mypy 报 `Unused "type: ignore"` 就是码写错了。

---

## 4. `edit` 工具本身（踩过 2 次）

### 4.1 替换范围过大，误删函数体

- **现象**：`_parse_utc`、`InternalError` 整段被删，`NameError` 连锁报错。
- **正确做法**：`old_string` 只取**足够唯一的短片段**（3–8 行），不要整段函数；改完立刻 `read` 确认上下文完整。
- **自查**：编辑后跑一次 `ruff check` + 导入测试，能第一时间抓到语法/引用错误。

### 4.2 `file changed since it was read`

- **正确做法**：先 `read` 再 `edit`，不要复用旧读取结果。

---

## 5. 环境与权限（踩过 6 次）

### 5.1 `npx` / `npm.ps1` 被执行策略挡

- **正确做法**：一律 `npx.cmd` / `npm.cmd`。

### 5.2 `pip install` 报 `[Errno 13] Permission denied ... pip-unpack-...`

- **正确做法**：同一命令加 `sandbox_permissions=danger-full-access` 重试；并把 `TEMP`/`TMP`/`--cache-dir` 指到 `D:\shedguard\.tmp\`。

### 5.3 `ensurepip` 建 venv 失败（`WinError 5` 删临时目录）

- **正确做法**：把 Anaconda 的 `Lib\site-packages\pip` 与 `pip-*.dist-info` 复制进 `.venv\Lib\site-packages`。

### 5.4 Expo / Chrome / git push 写系统目录被拒

- **正确做法**：`npx expo install`、`expo start`（写 `C:\Users\user\.expo`）、headless Chrome（IPC 命名管道）、`git push`（ssh-agent 管道）都需要 `danger-full-access`。
- **注意**：PowerShell 会把 git 的 stderr 进度当错误显示，**exit code 才是判据**。

### 5.5 npm 缓存目录不可写

- **正确做法**：`$env:npm_config_cache="D:\shedguard\.tmp\npm-cache"`。

### 5.6 `cd` 到含括号的目录（如 `(tabs)`）

- **现象**：`找不到接受实际参数"$null"`。
- **正确做法**：整体加引号 `cd "app\src\app\(tabs)"` 或改用 `-LiteralPath`。

---

## 6. 后端与数据模型（踩过 3 次，都是真 bug）

### 6.1 按 owner 过滤时丢掉 `pet_id IS NULL` 的设备级提醒

- **现象**：`test_alerts_api.py::TestUploadPipeline` 断言 1 条实得 0 条。
- **根因**：`AlertRepository.list` 用 `pet_id.in_(owned)`，把 `pet_id IS NULL` 的设备级提醒排除。
- **正确做法**：`or_(AlertRow.pet_id.is_(None), AlertRow.pet_id.in_(owned))`。

### 6.2 按 pet 过滤时同样丢掉设备级提醒（同类 bug 第二次）

- **现象**：`device_sim --pet-name` 上传后 App 日志页看不到提醒。
- **正确做法**：`or_(AlertRow.pet_id == pet_id, AlertRow.pet_id.is_(None))`，并加回归测试 `test_device_level_alert_visible_when_filtering_by_pet`。
- **教训**：**凡是「按某个外键过滤」的仓储方法，都要先问一句「为空的行该不该看见」**，并为两种情况各写一条测试。

### 6.3 推送被禁用时被误记成 `failed`

- **正确做法**：`deliver` 里对 `PushStatus.SKIPPED` 直接 `continue`；无 token 的目标也跳过（不记失败）。

---

## 7. 模型与训练（踩过 3 次）

### 7.1 `torch.onnx.export` 缺 `onnxscript`

- **正确做法**：`onnxscript>=0.2` 写进 `ml/requirements.txt`。

### 7.2 导出产生 `.onnx.data` 外部权重，沙箱 `rmdir` 失败

- **正确做法**：脚本里 `inline_external_data(target)`（`onnx.load` + `onnx.save` 并回单文件），命令加 `danger-full-access`。

### 7.3 评估与推理的预处理不一致

- **正确做法**：训练评估只用 `Resize((224,224))`、不做 `CenterCrop`，与服务端 `cv2.resize` 整图缩放保持一致。

---

## 8. 前端（React Native / Expo，踩过 4 次）

### 8.1 `Link asChild` 包 `Pressable` 会丢掉 style

- **现象**：卡片边框、横向排列、内边距全部失效，元素竖排。
- **正确做法**：不用 `Link`，改 `import { router } from 'expo-router'` + `onPress={() => router.push(...)}`。

### 8.2 `react-hooks/set-state-in-effect`

- **现象**：`useEffect(() => setX(...), [dep])` 被 lint 拒。
- **正确做法**：改成派生值（`const value = draft === '' ? source : draft;`），或用 `useQuery` 取代 effect 里 setState。

### 8.3 `Notifications.AndroidImportance` 在 eslint 下 `not found`

- **正确做法**：直接写字面量 `3` 并加注释说明。

### 8.4 样式数组漏了基础样式

- **现象**：`SecondaryButton` 只有 `styles.buttonSecondary`，渲染成贴边纯文字。
- **正确做法**：`[styles.button, styles.buttonSecondary, ...]`，基础样式永远在最前。

### 8.5 提交前忘回滚调试用临时改动

- **已发生**：`serverUrl.ts` 里把 `?? ''` 临时改成 `http://127.0.0.1:8130` 便于截图。
- **正确做法**：调试改动集中在一处并留 `// TODO(临时)` 标记；提交前 `git diff` 逐行过一遍。

### 8.6 新增路由后 `tsc` 报路径不存在

- **正确做法**：起一次 `$env:CI=1; npx expo start --web` 让它生成 `.expo/types/router.d.ts` 再 typecheck。

---

## 9. 依赖与 CI（踩过 1 次，影响最大）

### 9.1 `requirements.lock` 是从本地环境 freeze 的，含公开 PyPI 不存在的版本

- **现象**：CI 永远装不上；`numpy==2.5.4` 在 cp312/cp313/cp314 都找不到。
- **正确做法**：CI 与安装一律 `pip install -e ".[dev]"`（按 `pyproject.toml` 区间解析），lock 仅作本地复现记录；`AGENTS.md` §六.8 已固定此规则。
- **教训**：**任何「锁文件」都要在目标环境实测能装**，不要假设 freeze 出来的东西可分发。

---

## 10. 仓库卫生（踩过 1 次）

### 10.1 `.gitignore` 的 `*.png` 把 App 图标挡在仓库外

- **现象**：克隆后 App 缺图标，`git status` 却显示干净。
- **正确做法**：加例外 `!app/assets/` + `!app/assets/**`，并用 `git check-ignore -v <path>` 逐项确认。
- **教训**：**宽泛的通配规则必须配例外并实测**，否则「本地看着正常、克隆后坏掉」。

---

## 11. 流程（踩过 2 次）

### 11.1 在旧计划上直接开发

- **已发生**：产品切口从「预测」改为「检测」后，仍按旧 roadmap 推进了一小段。
- **正确做法**：`docs/plan.md` 是唯一权威；新方案第一步改它（§6 变更记录 + §3 里程碑 + §4 当前主线），再写规格等批准，最后才动代码。

### 11.2 文档数字与代码不同步

- **正确做法**：每次阶段收尾，同步 `docs/handoff.md`（状态快照）与 `docs/plan.md`（§3/§4）；数字以当场实测为准，改完 grep 一遍旧数字。

---

## 12. 维护约定

- 新增条目格式：**现象 → 根因 → 正确做法 → 自查**，四段齐全，写清「已发生几次」。
- 同一条错误第二次发生时，必须在本文件里升级为「高频」并考虑加自动化检查（测试、脚本、CI 步骤）。
- 本文件与 `AGENTS.md` §十二「遇到不确定时」互相引用，两边都要指向对方。

# 数据贡献收件箱配置手册（P29）

> 这份手册是给**你（项目维护者）**看的，不是给用户看的。
> 用户侧只需要在 App 里打开一个开关，之后照片会自动传到你这里；
> 你要做的是**先建好收件箱**（私有 HuggingFace 数据集仓库），再把两行配置填进服务端。

---

## 1. 这是什么

用户打开「帮助改进识别」后，他电脑上的服务端会把守宫照片（默认只有裁剪特写）自动上传到你的私有数据集仓库。

- 收件箱：`https://huggingface.co/datasets/<你的用户名>/<仓库名>`
- 免费、免服务器；仓库私有，只有你和拿到 token 的机器能写。

---

## 2. 前提

- 一个 HuggingFace 账号（免费注册：https://huggingface.co/join）
- 5 分钟

---

## 3. 步骤一：建一个**私有**数据集仓库

1. 打开 https://huggingface.co/new-dataset
2. **Dataset name** 填 `shedguard-contributions`（名字随你，记下来）
3. **Visibility 必须选 `Private`**（公开就等于把用户的照片公开了）
4. License 选 `other`
5. 点 **Create dataset**
6. 记下仓库 id，形如 `linzizhen/shedguard-contributions`

---

## 4. 步骤二：建一把「只能写这一个仓库」的钥匙

不要用你账号的全局 write token——那等于把整个账号交出去。用 **fine-grained token**：

1. 打开 https://huggingface.co/settings/tokens
2. **Create new token** → 类型选 **Fine-grained**
3. Token name 填 `shedguard-ingest`
4. **Repository permissions**：只勾选第 3 步建的那个 dataset，权限给 **Write**；其它仓库**一个都不要勾**
5. 点 **Create token**，复制 `hf_` 开头的那串（**只显示一次**，页面关掉就得重建）

---

## 5. 步骤三：填进服务端配置

在 `server/.env` 里加三行（没有 `.env` 就从 `server/.env.example` 复制一份再改）：

```dotenv
SHEDGUARD_CONTRIBUTION_UPLOAD_ENABLED=true
SHEDGUARD_CONTRIBUTION_UPLOAD_REPO=你的用户名/shedguard-contributions
SHEDGUARD_CONTRIBUTION_UPLOAD_TOKEN=hf_粘贴刚才那串
```

注意：

- `.env` 已经被 `.gitignore` 忽略，**不要把 token 提交进仓库**（也不要贴进聊天记录、issue、截图）。
- 这三行**只影响上传**；没填时功能照常工作，只是样本留在本机标记「等待上传」。
- 用户那台电脑上也要有一份 `server/.env`；分发给普通用户时，等于把 token 放在用户机器上——所以务必按第 4 步收敛权限，出事时直接吊销这把 token 重发。

---

## 6. 步骤四：验证通路

1. 重启服务端：
   ```powershell
   cd server
   $env:PYTHONPATH="D:\shedguard\server\src"
   ..\.venv\Scripts\python.exe -m shedguard_server
   ```
2. App → 我的 → 帮助改进识别 → **打开开关**
3. 灌一张蜕皮照片（真机抓拍，或用模拟脚本）：
   ```powershell
   ..\.venv\Scripts\python.exe scripts\device_sim.py --base-url http://127.0.0.1:8000 --image ..\ml\datasets\gecko-state-v2\test\shedding\<任意一张>.jpg --pet-name 小橙
   ```
4. 等 30 秒 ~ 1 分钟（上传循环默认 30 分钟一次；急着测可把 `SHEDGUARD_CONTRIBUTION_UPLOAD_MINUTES` 临时设成 1）
5. 打开 `https://huggingface.co/datasets/<仓库>/tree/main`，应该能看到：
   ```
   <owner_hash>/2026-11-16/<sha12>.jpg
   <owner_hash>/2026-11-16/<sha12>.json
   ```

命令行快速核对：

```powershell
..\.venv\Scripts\python.exe -c "import os;from huggingface_hub import HfApi;print(HfApi().list_repo_files(os.environ['SHEDGUARD_CONTRIBUTION_UPLOAD_REPO'], repo_type='dataset')[:10])"
```

---

## 7. 步骤五：把数据拉下来入库

收件箱里是「一次蜕皮事件的一小撮图」，攒到一定量后再入库：

1. 下载仓库（`huggingface-cli download <仓库> --repo-type dataset --local-dir data/hf_contributions`）
2. 按 `.json` 里的 `state` 分拣：`shedding` → 加入训练集；`normal` → 加入负样本
3. **人工抽检**（同 `docs/data-search-2026-11-09.md` 的复核流程）：模型标签会有噪声，先看一批再入正式数据集
4. 入库后按 P22 的脚本重跑一次鲁棒性评估，确认没退化

> 自动化脚本（`ml/import_contributions.py`）留到有实际数据后再写，避免先写空转的工具。

---

## 8. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 仓库里一直没有文件 | ① `SHEDGUARD_CONTRIBUTION_UPLOAD_ENABLED` 还是 false；② App 里的开关没打开（默认关）；③ 服务端日志有上传失败行 |
| 报 401 / 403 | token 权限不对（没给该仓库 Write），或仓库名写错 |
| 一直显示「待上传」 | 上传连续失败 5 次会被标记失败并停止重试；看服务端日志的 `贡献上传失败` 行 |
| 用户说「我关了开关还在传」 | 后台只会传 `pending` 的存量；关开关不影响已在队列里的样本——要么等它传完，要么在页面点「全部清空」 |
| 想立刻看效果 | 把 `SHEDGUARD_CONTRIBUTION_UPLOAD_MINUTES` 临时设为 1，验证完改回 30 |

---

## 9. 安全提醒（每次改这块都要回头看一遍）

- 仓库**必须** Private。
- token **必须** fine-grained，且只勾这一个仓库、只给 Write。
- token 泄露 → 立即到 https://huggingface.co/settings/tokens 删掉那把，重发一把，并更新用户机器上的 `.env`。
- 上传内容默认只有裁剪特写、不含宠物名/设备号/原文件名；服务端日志也不打印 token。
- 撤回是「尽力删除远端」：用户点撤回时我们会调 HF 删除接口，但仓库的**提交历史**里可能还留着旧版本，真正清除需要你在仓库设置里做版本清理。

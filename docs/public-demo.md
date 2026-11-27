# 把 ShedGuard 变成一个能发给别人的网址

> 面向：想把 App 发给朋友试用、或用自己手机（不连家里 Wi-Fi）试一遍的人。
> 一条命令，本机服务端 + 前端页面会一起出现在一个 `https://` 网址上。
> 关联规格：`docs/specs/2026-11-19-public-access-design.md`；计划项：`docs/plan.md` P33。

---

## 1. 一句话原理

以前要跑两个东西：一个只给接口的服务端（`127.0.0.1:8000`），一个只在开发机上看的网页（Metro `:8081`），手机还得手填内网 IP。

现在服务端**自己也会发网页**：同一个地址，`/api/v1/...` 是接口，其他路径是页面。再用 Cloudflare 的免费隧道把它搬到公网，手机用流量就能打开，**不需要填任何地址**。

```
手机（4G/5G）
   ↓ https://xxx.trycloudflare.com
Cloudflare 快速隧道
   ↓ http://127.0.0.1:8010
本机服务端（同时发页面 + 接口）
```

---

## 2. 第一次用

前置：仓库已经能跑（`.venv` 装好、`server/.env` 有内容）。只需要跑一条：

```powershell
.\scripts\serve-public.cmd
```

它会依次做四件事，每步都会打印进度：

1. 构建前端（`app/dist` 不存在时才做，约 1–3 分钟；产物约 1.9 MB）；
2. 起服务端（端口 `8010`，限流 60 次/分）；
3. 等 `/healthz` 返回 `ok`（最多 90 秒）；
4. 起隧道并打印网址。

看到这样一段就成功了：

```
  公网网址：https://bend-bald-frequently-dominant.trycloudflare.com

  把这个网址发到手机上打开即可（不需要填任何服务器地址）。
```

**第一次跑会多花约 1 分钟下载 `cloudflared.exe`（约 55 MB）到 `.tmp/`，之后不再下载。**

---

## 3. 常用参数

| 参数 | 作用 | 例子 |
| --- | --- | --- |
| `-Port 8020` | 换服务端端口（默认 8010） | 端口被占用时 |
| `-Rebuild` | 强制重新构建前端 | 改了 App 代码之后 |
| `-SkipTunnel` | 不起隧道，只在本机/局域网看 | 只想自己看看 |
| `-RateLimitPerMinute 30` | 换限流阈值（默认 60） | 想更保守 |

只想单起一条隧道（服务端已经自己在跑）：

```powershell
.\scripts\tunnel.cmd -Port 8010
```

---

## 4. 怎么关

在跑脚本的那个窗口按 **Ctrl+C**。隧道与服务端会被一起停掉，不留后台进程。

如果窗口被直接关掉（比如关了终端标签），可能留下孤儿进程，用这个查：

```powershell
Get-Process cloudflared,python -ErrorAction SilentlyContinue
```

有就手动结束：`Stop-Process -Id <PID>`。

---

## 5. 四件必须知道的事

### 5.1 网址每次都不一样

免费快速隧道不绑域名，**每次启动换一个随机网址**。旧网址立刻失效，需要重新发。

要固定网址得用 Named Tunnel，那需要自有域名（本设计不做，见规格 §2 非目标）。

### 5.2 这个链接等于家门钥匙

拿到链接的人可以：建匿名账号、上传图片、看自己上传的记录。**不要发到公开群、论坛、社交媒体。**

目前的门禁只有两条：限流 60 次/分、单图 10 MB。没有密码、没有邀请码。

### 5.3 电脑关机就断

服务跑在你自己电脑上。电脑睡眠/关机/断网 → 网址立刻打不开。想长期在线只能迁到云服务器（同一套服务端，不用改代码）。

### 5.4 暴露期间的数据是真的

上传的图片会真的落盘到 `server` 的数据目录、真的跑判定、真的进日志。演示完想清干净，删掉数据目录即可（默认在 `server/data`，演示脚本没改这个）。

---

## 6. 页面能做什么、不能做什么

打开网址就是一个完整的 Web App：

- 欢迎向导 → 起名字 → 拍照或选图 → 看结论 → 日志里看历史；
- 摄像头、萌照、分享照片、风险自测都在；
- **拍得不清楚时会直接说「这张有点糊 / 光线太暗了 / 太亮了，看不清 / 没找到守宫」并给对应建议**，而不是硬给一个结论（输入质量门，见下）；
- **浏览器里没有系统推送**（远程推送需要装 APK 且手机带 Google 服务，见 `docs/push-setup.md`），但「日志」页会轮询，提醒横幅照样能看到。

### 6.1 演示前请打开输入质量门

质量门在代码里**默认是关闭的**（因为测试用纯色块当上传图，一开门会全被拒）。对外演示时把它打开，别人随手拍一张糊图才不会看到「它正在蜕皮」这种离谱结论：

```powershell
$env:SHEDGUARD_QUALITY_GATE_ENABLED = 'true'
.\scripts\serve-public.cmd
```

更稳妥的做法是写进 `server/.env`（本机已打开），启动日志会打印「输入质量门已启用 sharpness>=25.0 lightness>=18.0 saturated<=0.2」；没打印就是没生效。

四条门与阈值：太糊（拉普拉斯方差 < 25）、太暗（L\* 均值 < 18）、过曝（近白像素占比 > 0.20）、没拍到守宫（检测为空）。阈值来自网图标定，真实饲养箱数据还没验过，见 `docs/plan.md` §7。

---

## 7. 出问题怎么查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面 404，但 `/api/v1/pets` 正常 | `app/dist` 不存在 | 加 `-Rebuild` 重跑，或 `cd app; npm.cmd run build:web` |
| 启动报「端口被占用」 | 上次没退干净 | `Get-NetTCPConnection -LocalPort 8010` 找 PID 结束，或换 `-Port` |
| 隧道 60 秒没给网址 | 网络到 Cloudflare 不通 | 看 `.tmp/tunnel-*.err.log` 尾部；公司网络可能拦了 |
| 手机打开是白屏 | 浏览器缓存了旧 `index.html` | 强刷；或换无痕窗口 |
| 手机能开页面但请求全失败 | 隧道断了（免费隧道会掉） | 重启脚本，拿新网址 |
| 中文乱码 | PowerShell 控制台按 ANSI 解码 | 设 `$env:PYTHONIOENCODING='utf-8'`；文件本身没坏 |

日志位置：

- 服务端：`.tmp/server-public-<端口>.log` 与 `.err.log`
- 隧道：`.tmp/tunnel-<时间戳>.out.log` 与 `.err.log`

---

## 8. 验收清单（发出去之前自己过一遍）

- [ ] 手机**关掉 Wi-Fi**，用流量打开网址 → 首页正常显示
- [ ] 选一张图 → 得到结论（不是「看不清」以外的报错）
- [ ] 「日志」页能看到刚才这条记录
- [ ] 全程没有让填过任何服务器地址
- [ ] `https://<网址>/docs` 能打开接口文档
- [ ] `https://<网址>/api/v1/does-not-exist` 返回 JSON 404（不是网页）

最后两条是确认「API 没被页面兜底路由吞掉」。

---

## 9. 脚本清单

| 文件 | 作用 |
| --- | --- |
| `scripts/serve-public.cmd` / `.ps1` | 一键：构建 → 起服务 → 起隧道 → 打印网址 |
| `scripts/tunnel.cmd` / `.ps1` | 只起隧道 |
| `scripts/tunnel-lib.ps1` | 两者共用的函数（找 python、下载 cloudflared、起停进程） |
| `scripts/fetch_cloudflared.py` | 用 venv 的 Python 下载 cloudflared（PowerShell 的 `Invoke-WebRequest` 在本机证书链有问题） |
| `scripts/spawn_bg.py` | 后台起进程（PowerShell 的 `Start-Process` 在本机因环境变量重名会抛异常） |

> 两个 `.ps1` 必须存成 **UTF-8 带 BOM**，否则 PowerShell 5.1 会按 GBK 解码报 `Unexpected token`；两个 `.cmd` 必须**纯 ASCII**。改完记得检查。

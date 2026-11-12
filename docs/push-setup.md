# 推送真链路配置（P18）

> 目的：让手机真正收到「守宫正在蜕皮 / 设备可能离线」的系统通知，而不是只在 App 里看到提醒列表。
> 适用范围：Expo SDK 58 + `expo-notifications`。**Expo Go 不支持远程推送**，必须做 development build（自定义客户端）。

## 0. 你会得到什么

- 一个可安装到手机的 App（APK / IPA），打开后不再依赖 Expo Go；
- App 在「设置 → 摄像头与提醒」里点「保存并启用通知」后，会把 Expo Push Token 上报到服务端；
- 服务端产生提醒时调用 `https://exp.host/--/api/v2/push/send`，手机收到系统通知，点开进入提醒详情。

App 端在拿不到 token 时（Expo Go、网页、未配置 projectId）会退化为「只在提醒列表里显示」，不会报错。

## 1. 前提

| 项 | 要求 |
|---|---|
| Expo 账号 | 免费账号即可（https://expo.dev/signup） |
| 手机 | Android 8+（推荐，打 APK 最快）或 iPhone（需 Apple 开发者账号才能装到真机） |
| 电脑 | 本仓库 + Node 24；EAS 构建在云端跑，不需要本地 Android SDK |
| 服务端 | 手机与服务器在同一局域网，`http://<电脑局域网 IP>:8000` 可访问（防火墙放行 8000） |

## 2. 一次性初始化（在 `app/` 目录）

```powershell
cd app
npm install -g eas-cli          # 只需一次
eas login                        # 用你的 Expo 账号登录（凭据只在你本机）
eas init                         # 关联/创建 EAS 项目，自动把 projectId 写进 app.json 的 extra.eas.projectId
```

`eas init` 会问是否创建新项目，选「Yes」并在 Expo 控制台确认。完成后 `app.json` 里会多出：

```json
"extra": { "eas": { "projectId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" } }
```

> 本仓库的 `app/eas.json` 已含 `development` / `preview` / `production` 三个 profile，
> `development` 打开 `developmentClient: true` 并输出 APK，无需再改。

## 3. 打 development build（在 `app/` 目录）

```powershell
eas build -p android --profile development
```

- 首次会问是否生成 keystore，选「Yes，让 EAS 生成」；
- 构建约 10–20 分钟，结束后终端给一个 APK 下载链接/二维码；
- 用手机浏览器打开链接安装（Android 需允许「安装未知来源应用」）。

iPhone 用户：`eas build -p ios --profile development`，需要 Apple 开发者账号并把设备 UDID 注册进 profile。

## 4. 启动与首次绑定

1. 手机装上 App，确保与电脑同一 Wi-Fi；
2. App「设置」页填服务器地址 `http://<电脑局域网 IP>:8000`，点「测试连接」应显示成功；
3. 「摄像头与提醒」卡片填设备编号（与固件 `APP_DEVICE_ID` 一致，如 `gecko-eye-01`），选好绑定宠物，点「保存并启用通知」；
4. 系统弹通知权限 → 允许；成功后卡片显示已启用的 token 前缀。

## 5. 验证真的能收到

先确认服务端能把提醒发出去（绕过相机，直接造一条蜕皮提醒）：

```powershell
cd server
$env:PYTHONPATH="server\src"
.\.venv\Scripts\python.exe -m shedguard_server      # 另开一个窗口常驻
```

```powershell
# 另开窗口：用你的 token 直接打 Expo 推送接口
$token = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"   # App 设置页显示的那个
$body = @(@{ to = $token; title = "守宫正在蜕皮"; body = "这是一条测试推送"; data = @{ kind = "shedding_detected" } }) | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "https://exp.host/--/api/v2/push/send" -Method Post -ContentType "application/json" -Body $body
```

手机应在几秒内收到通知。收不到就按第 6 节排查。

真实链路验证：让固件/脚本上传一张蜕皮照片（`POST /api/v1/images`，头带 `X-Device-Id`），
服务端会自动分析 → 状态为 shedding 且前一日非 shedding → 建提醒 → 推送。
`SHEDGUARD_PUSH_ENABLED=false` 时只建提醒不推送（本地联调默认值请确认是 `true`）。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 设置页提示「需要 EAS 构建（development build）并配置 projectId」 | 还在 Expo Go 里跑，或没执行 `eas init`。先完成第 2、3 节 |
| 推送返回 `DeviceNotRegistered` | token 失效（重装 App / 换设备）。服务端会自动删除该 token，App 重新点一次启用即可 |
| 手机收不到，但 Expo 返回 `status: ok` | 检查系统通知权限、勿扰模式；Android 需允许「通知」与「后台运行」 |
| App 里请求全部失败（Network request failed） | 手机与电脑不在同一网段，或 Windows 防火墙拦了 8000；用 `ipconfig` 查电脑 IP |
| Android 上 HTTP 请求被拒（明文流量） | 已在 `app.json` 通过 `expo-build-properties` 开 `usesCleartextTraffic`（**仅开发**）；正式发布必须换 HTTPS |
| iPhone 装不上 | 需要 Apple 开发者账号（$99/年）并把设备注册进 provisioning profile |

## 7. 已知限制

- 本方案仍走 HTTP 明文 + 无 HTTPS，只适合家庭局域网开发联调；
- Token 存在服务端 `push_devices` 表，明文 AsyncStorage 保存账号令牌，属于现有欠账；
- EAS 免费额度有限（每月构建次数），不要频繁重打；
- iOS 真机分发门槛较高，优先用 Android 验证链路。

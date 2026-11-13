# ShedGuard App

豹纹守宫蜕皮助手：拍照查验蜕皮状态、查看设备自动推送的蜕皮提醒、记录蜕皮日志、饲养知识库、卡皮风险评估。

技术栈：Expo SDK 58 + React Native 0.88 + TypeScript + Expo Router + React Query。

## 前置条件

- Node.js ≥ 20
- 电脑上跑着 ShedGuard 服务端（`server/`），App 通过局域网访问它的 HTTP 接口
- 手机装 [Expo Go](https://expo.dev/go)（开发期预览用，无原生模块时够用）；无 Google 服务的国产安卓机装不了，改用网页版预览

## 快速开始

```bash
npx expo install        # 安装依赖（首次）
npx expo start          # 起开发服务
```

手机 Expo Go 扫终端二维码即可预览。开发服务启动后 `tsc` 的 typed routes 类型（`.expo/types/`）会自动生成。

> 也可以在电脑浏览器预览：`npx expo start --web`，打开 `http://localhost:8081`。
> 注意浏览器预览从「网页」跨域请求后端，若服务端未开 CORS 会失败；手机 Expo Go 走原生请求，无跨域问题，是推荐方式。

### 要收推送通知：必须打 development build

Expo Go 不支持远程推送。要真机收到蜕皮提醒，用 `app/eas.json` 里的 `development` profile 打包：

```bash
npm install -g eas-cli
eas login && eas init          # 写入 extra.eas.projectId
eas build -p android --profile development
```

完整步骤与排错见 [docs/push-setup.md](../docs/push-setup.md)。未打包时 App 仍可正常使用，只是提醒只在列表里显示。

## 首次配置

App 第一次打开会走三步向导（欢迎 → 给守宫起名字 → 准备拍照），每一步都能跳过。向导里如果还没有服务器地址，会先让你填一次「电脑上那个程序的地址」。

之后所有技术项都收在「我的 → 高级设置」里，普通使用不需要碰。

## 功能

| Tab | 功能 | 后端接口 |
|-----|------|----------|
| 拍照（首页） | 一个圆形大按钮「拍张照」+ 从相册选；结果只显示一句人话结论与建议，置信度与概率收进折叠的「看看更多细节」；有萌照时顶部显示「今天的萌照」卡片 | `POST /api/v1/pets/{id}/check-photo`、`GET /api/v1/pets/{id}/portraits/today` |
| 蜕皮记录 | 顶部提醒横幅（蜕皮 / 设备离线 / 看不到守宫三类，点开看详情）、蜕皮时间线、记一次蜕皮 / 标记蜕完 / 删除、卡皮风险评估入口 | `GET /api/v1/alerts`、`GET/POST/PUT/DELETE /api/v1/pets/{id}/shed-records` |
| 我的 | 我的守宫（列表 + 添加）、蜕皮提醒（摄像头编号 + 保存并开启通知）、萌照相册与萌照设置入口、蜕皮知识入口、卡皮检查入口、折叠的「高级设置」（服务器地址 + 重置身份） | `GET /healthz`、`/api/v1/pets` CRUD、`POST/DELETE /api/v1/devices` |
| 萌照（首页 / 我的进入） | 每天的近景成品图，可「这张好看」/「不太满意」；相册按日期三列网格；设置里改开关、每天张数、起止时间 | `GET /api/v1/pets/{id}/portraits[/today]`、`POST /api/v1/portraits/{id}/feedback`、`GET/PUT /api/v1/pets/{id}/portrait-settings` |
| 蜕皮知识（从「我的」进入） | 六个话题卡片与详情 | `GET /api/v1/knowledge/topics[/{slug}]` |
| 提醒详情（记录页进入） | 显示抓拍原图、日期、判定与置信度，打开即标记已读 | `GET /api/v1/images/{id}`、`PATCH /api/v1/alerts/{id}` |
| 卡皮风险（记录页进入） | 六题问卷 → 风险评分与分级、就医警示 | `POST /api/v1/risk-assessment` |

## 目录结构

```
app/
├── src/
│   ├── app/                    # Expo Router 文件路由
│   │   ├── _layout.tsx         # 根布局：QueryClient + Stack + 通知桥 + 首启向导跳转
│   │   ├── welcome.tsx         # 三步首次向导
│   │   ├── knowledge.tsx       # 蜕皮知识列表（从「我的」进入）
│   │   ├── (tabs)/             # 底部三 Tab
│   │   │   ├── _layout.tsx     # Tab 导航器（拍照 / 蜕皮记录 / 我的）
│   │   │   ├── index.tsx       # 拍照查验
│   │   │   ├── log.tsx         # 蜕皮记录 + 提醒横幅 + 风险评估入口
│   │   │   └── settings.tsx    # 我的：守宫、提醒、知识入口、高级设置
│   │   ├── pet/                # 宠物表单页（Stack）
│   │   │   ├── new.tsx         # 添加宠物
│   │   │   └── [id].tsx        # 编辑/删除宠物
│   │   ├── alert/[id].tsx      # 蜕皮提醒详情（抓拍原图 + 标记已读）
│   │   ├── topic/[slug].tsx    # 知识详情
│   │   └── risk.tsx            # 卡皮风险评估问卷
│   ├── components/             # ui.tsx 黏土风基础件、PetForm、PetPicker
│   ├── hooks/                  # React Query hooks（usePets / useShed / useKnowledge / useRisk / useAlerts）
│   └── lib/                    # theme / api / auth / serverUrl / deviceId / onboarding / resultCopy / types / dates
├── app.json                    # Expo 配置（CNG，勿手建 ios/android）
└── tsconfig.json               # strict + @/* 路径别名
```

## 质量门

```bash
npx tsc --noEmit   # 类型检查
npx eslint .       # 代码检查
```

完成任何功能前两者必须全绿。

## 对接的后端接口

| 接口 | 用途 | 状态 |
|------|------|------|
| `GET /healthz` | 测试连接 | 已接 |
| `POST /api/v1/users/anonymous`、`GET /api/v1/users/me` | 匿名账号：首次启动自动领取令牌，后续请求带 `Authorization: Bearer` | 已接 |
| `GET/POST /api/v1/pets`、`PUT/DELETE /api/v1/pets/{id}` | 宠物档案 CRUD | 已接 |
| `POST /api/v1/pets/{id}/check-photo` | 拍照查验 | 已接 |
| `GET/POST/PUT/DELETE /api/v1/pets/{id}/shed-records` | 蜕皮日志 | 已接 |
| `GET /api/v1/pets/{id}/shed-prediction` | 下次蜕皮预测（已弃用，App 不再展示） | 保留 |
| `GET /api/v1/alerts`、`PATCH /api/v1/alerts/{id}` | 蜕皮提醒列表与已读 | 已接 |
| `POST /api/v1/devices`、`DELETE /api/v1/devices/{id}` | 推送设备注册与解绑 | 已接 |
| `GET /api/v1/knowledge/topics`、`/topics/{slug}` | 知识库 | 已接 |
| `POST /api/v1/risk-assessment` | 卡皮风险评估 | 已接 |

## 调试与预览

- **网页版预览**：`npx expo start --web`，浏览器打开 Metro 地址即可（手机浏览器同网段也能开）。服务端需设 `SHEDGUARD_CORS_ORIGINS=*` 才允许跨域。
- **预填服务器地址**：开发时可用环境变量 `EXPO_PUBLIC_SERVER_URL=http://<电脑局域网IP>:8000 npx expo start`，App 首次启动会自动填入该地址，省去手输；正式包该变量留空。
- **Expo Go**：需要 Google 服务的安卓机或 iPhone；国内无 GMS 的机型（如部分荣耀/华为）商店可能没有，此时用网页版预览。

## 已知限制

- 账号：本机匿名令牌（Bearer），宠物按账号隔离；换机或清数据会丢失账号，历史宠物看不到
- 仍无 HTTPS：令牌在局域网内明文传输；令牌明文存 AsyncStorage
- 服务器地址、设备编号明文存 AsyncStorage
- 蜕皮状态分类器目前只有「正常 / 蜕皮中」两类，蒙白（opaque）暂无训练样本，会出现但概率低；分类准确性受网图训练数据限制
- 推送依赖 Expo Push 服务与外网；Web 浏览器不支持推送，仅原生 App 可用
- 周期预测已下线（`shed-prediction` 接口保留但 App 不再使用）

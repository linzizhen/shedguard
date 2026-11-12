# ShedGuard App

豹纹守宫蜕皮助手：拍照查验蜕皮状态、查看设备自动推送的蜕皮提醒、记录蜕皮日志、饲养知识库、卡皮风险评估。

技术栈：Expo SDK 58 + React Native 0.88 + TypeScript + Expo Router + React Query。

## 前置条件

- Node.js ≥ 20
- 电脑上跑着 ShedGuard 服务端（`server/`），App 通过局域网访问它的 HTTP 接口
- 手机装 [Expo Go](https://expo.dev/go)（开发期预览用，无原生模块时够用）

## 快速开始

```bash
npx expo install        # 安装依赖（首次）
npx expo start          # 起开发服务
```

手机 Expo Go 扫终端二维码即可预览。开发服务启动后 `tsc` 的 typed routes 类型（`.expo/types/`）会自动生成。

> 也可以在电脑浏览器预览：`npx expo start --web`，打开 `http://localhost:8081`。
> 注意浏览器预览从「网页」跨域请求后端，若服务端未开 CORS 会失败；手机 Expo Go 走原生请求，无跨域问题，是推荐方式。

## 首次配置

1. 打开 App →「设置」Tab
2. 填服务端地址（电脑局域网 IP，如 `http://192.168.1.100:8000`）→ 保存 → 测试连接
3. 「宠物管理」→ 添加第一只守宫
4. 「摄像头与提醒」→ 填设备编号（与固件 `APP_DEVICE_ID` 一致）→ 绑定宠物 → 保存并启用通知（iOS/Android 会申请通知权限；Web 浏览器不支持推送）

## 功能

| Tab | 功能 | 后端接口 |
|-----|------|----------|
| 拍照查验 | 选宠物 → 拍照/相册 → 上传判定蜕皮状态（正常/蒙白/蜕皮中/无法判断），显示置信度、概率分布与护理建议 | `POST /api/v1/pets/{id}/check-photo` |
| 蜕皮日志 | 宠物切换、顶部蜕皮提醒横幅（设备自动检测到蜕皮时出现，点开看原图）、蜕皮记录时间线、添加/标记完成/删除、卡皮风险评估入口 | `GET /api/v1/alerts`、`GET/POST/PUT/DELETE /api/v1/pets/{id}/shed-records` |
| 知识 | 六个话题卡片（速览/环境/喂食/蜕皮基础/卡皮处理/加湿）与详情 | `GET /api/v1/knowledge/topics[/{slug}]` |
| 设置 | 服务器地址配置与连通性测试、宠物档案管理、设备编号绑定与推送通知启用 | `GET /healthz`、`/api/v1/pets` CRUD、`POST/DELETE /api/v1/devices` |
| 提醒详情（日志页进入） | 显示抓拍原图、日期、判定与置信度，打开即标记已读 | `GET /api/v1/images/{id}`、`PATCH /api/v1/alerts/{id}` |
| 卡皮风险（日志页进入） | 六题问卷 → 风险评分与分级、就医警示 | `POST /api/v1/risk-assessment` |
| 知识详情（知识页进入） | 话题分段正文 | `GET /api/v1/knowledge/topics/{slug}` |

## 目录结构

```
app/
├── src/
│   ├── app/                    # Expo Router 文件路由
│   │   ├── _layout.tsx         # 根布局：QueryClient + Stack（注册 pet/topic/risk/alert）+ 通知桥
│   │   ├── (tabs)/             # 底部四 Tab
│   │   │   ├── _layout.tsx     # Tab 导航器
│   │   │   ├── index.tsx       # 拍照查验
│   │   │   ├── log.tsx         # 蜕皮日志 + 提醒横幅 + 风险评估入口
│   │   │   ├── knowledge.tsx   # 知识话题列表
│   │   │   └── settings.tsx    # 服务器地址 + 宠物管理 + 设备与通知
│   │   ├── pet/                # 宠物表单页（Stack）
│   │   │   ├── new.tsx         # 添加宠物
│   │   │   └── [id].tsx        # 编辑/删除宠物
│   │   ├── alert/[id].tsx      # 蜕皮提醒详情（抓拍原图 + 标记已读）
│   │   ├── topic/[slug].tsx    # 知识详情
│   │   └── risk.tsx            # 卡皮风险评估问卷
│   ├── components/             # ui.tsx 黏土风基础件、PetForm、PetPicker
│   ├── hooks/                  # React Query hooks（usePets / useShed / useKnowledge / useRisk / useAlerts）
│   └── lib/                    # theme / api / serverUrl / deviceId / types / dates
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

## 已知限制

- 账号：本机匿名令牌（Bearer），宠物按账号隔离；换机或清数据会丢失账号，历史宠物看不到
- 仍无 HTTPS：令牌在局域网内明文传输；令牌明文存 AsyncStorage
- 服务器地址、设备编号明文存 AsyncStorage
- 蜕皮状态分类器目前只有「正常 / 蜕皮中」两类，蒙白（opaque）暂无训练样本，会出现但概率低；分类准确性受网图训练数据限制
- 推送依赖 Expo Push 服务与外网；Web 浏览器不支持推送，仅原生 App 可用
- 周期预测已下线（`shed-prediction` 接口保留但 App 不再使用）

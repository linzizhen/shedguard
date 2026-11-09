# ShedGuard App

豹纹守宫蜕皮助手：拍照查验蜕皮状态、记录蜕皮日志、预测下一次蜕皮、饲养知识库。

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

## 首次配置

1. 打开 App →「设置」Tab
2. 填服务端地址（电脑局域网 IP，如 `http://192.168.1.100:8000`）→ 保存 → 测试连接
3. 「宠物管理」→ 添加第一只守宫

## 目录结构

```
app/
├── src/
│   ├── app/                  # Expo Router 文件路由
│   │   ├── _layout.tsx       # 根布局：QueryClient + Stack
│   │   ├── (tabs)/           # 底部四 Tab
│   │   │   ├── _layout.tsx   # Tab 导航器
│   │   │   ├── index.tsx     # 拍照查验（骨架）
│   │   │   ├── log.tsx       # 蜕皮日志（骨架）
│   │   │   ├── knowledge.tsx # 知识（骨架）
│   │   │   └── settings.tsx  # 设置：服务器地址 + 宠物管理（已实现）
│   │   └── pet/              # 宠物表单页（Stack）
│   │       ├── new.tsx       # 添加宠物
│   │       └── [id].tsx      # 编辑/删除宠物
│   ├── components/           # 复用组件（ui.tsx 黏土风基础件、PetForm）
│   ├── hooks/                # React Query hooks（usePets）
│   └── lib/                  # 基础设施（theme / api / serverUrl / types）
├── app.json                  # Expo 配置（CNG，勿手建 ios/android）
└── tsconfig.json             # strict + @/* 路径别名
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
| `GET/POST /api/v1/pets`、`PUT/DELETE /api/v1/pets/{id}` | 宠物档案 CRUD | 已接 |
| `POST /api/v1/pets/{id}/check-photo` | 拍照查验 | 待接 |
| `GET/POST /api/v1/pets/{id}/shed-records` 等 | 蜕皮日志与预测 | 待接 |
| `GET /api/v1/knowledge/topics` 等 | 知识库 | 待接 |
| `POST /api/v1/risk-assessment` | 卡皮风险 | 待接 |

## 已知限制

- 无鉴权：服务端与 App 都假定家庭局域网环境
- 拍照查验、日志、知识、风险四屏目前是占位骨架，逐屏开发中
- 服务器地址明文存 AsyncStorage

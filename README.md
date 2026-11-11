# shedguard

> 爬宠蜕皮监测：设备定时抓拍 → 服务端自动判定「正在蜕皮」→ App 提醒主人查看与护理。

## 一句话

**它要蜕皮了，你先知道。**

## 要解决的问题

爬宠（豹纹守宫、肥尾守宫等）蜕皮期湿度不够就会**卡皮**，导致趾头、尾巴坏死甚至死亡；而新手常常看不出「它正在蜕皮」。现有产品多在解决「环境稳不稳定」（温湿度监控、自动控温喷雾），却没人回答一个更具体的问题：**它现在是不是在蜕皮？**

## 解决方案

一套「摄像头 + 服务端 + 手机 App」的闭环：

1. **设备定时抓拍**：ESP32-S3-EYE 在白天窗口（默认 08:00–20:00）每 30 分钟拍一张，上传到服务端
2. **服务端自动判定**：检测守宫 → 裁剪 → 蜕皮状态分类（正常 / 蜕皮中），判定为「正在蜕皮」且相比前一状态发生跃迁时生成提醒
3. **手机提醒**：通过 Expo 推送通知，App 里能看到抓拍原图与判定结果，并记录蜕皮日志、查阅护理知识、做卡皮风险评估

产品是「外挂」式的：夹在饲养箱玻璃上的支架 + 摄像头，成本低，不改变现有饲养方式。

## 项目现状

| 模块 | 状态 | 说明 |
|------|------|------|
| 后端服务（FastAPI + SQLite） | 完成 | 收图去重、体表指标、序列与事件、宠物档案、日志、知识库、风险问卷、提醒流水线；340 测试 / 覆盖率 96% |
| 守宫检测模型 | 完成 | YOLO 导出 ONNX，测试集 mAP50 0.902 |
| 蜕皮状态分类器 | 完成（两态） | 正常 / 蜕皮中，测试准确率 0.9286 |
| React Native App | 完成 | 拍照查验、蜕皮日志、知识、设置四屏 + 蜕皮提醒详情与推送注册 |
| ESP32-S3-EYE 固件 | 代码完成，未上板 | WiFi、NTP、定时抓拍、multipart 上传、断网补传队列，`idf.py build` 通过 |
| 真实饲养箱数据 | 缺口 | 尚无自采照片；蒙白（opaque）样本为零 |

完整的阶段计划与决策记录见 [`docs/handoff.md`](docs/handoff.md) 与 [`docs/roadmap.md`](docs/roadmap.md)。

## 目录结构

```
shedguard/
├── docs/        # 产品、算法、规格与交接文档
├── firmware/    # ESP32-S3-EYE 固件（ESP-IDF）
├── server/      # 后端：收图、分析、判定、提醒（FastAPI + SQLite）
├── app/         # 手机 App（Expo + React Native + TypeScript）
└── ml/          # 模型训练脚本（检测器 + 状态分类器）
```

## 快速开始

### 后端

```bash
cd server
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.lock
python -m shedguard_server        # 默认监听 127.0.0.1:8000，启动时自动跑迁移
```

### App

```bash
cd app
npx expo install
npx expo start          # 手机装 Expo Go 扫码预览
```

### 固件

见 [`firmware/README.md`](firmware/README.md)，需要 ESP-IDF v5.4 环境。

## 质量门

- 后端：`ruff check src tests`、`mypy src tests`、`pytest`（覆盖率门槛 85%）全绿
- App：`npx tsc --noEmit`、`npx eslint .` 全绿

## 下一步

1. 固件上板联调（手边暂无实物）：验证相机出图、白天窗口、断网补传
2. 用真实饲养箱照片校准现场光照与阈值
3. 积累蒙白样本后训练三态分类器

## 已知限制

- 无鉴权、无 HTTPS：假定家庭局域网环境
- 分类器只有「正常 / 蜕皮中」两类，蒙白暂无训练样本；准确性受网图训练数据限制
- 固件尚未在真实硬件上运行验证
- 推送依赖 Expo Push 服务与外网

## 免责声明

本项目尚在验证阶段，所有健康相关建议只给行动参考，不做诊断，不替代异宠医生。

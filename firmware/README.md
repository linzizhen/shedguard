# firmware

ESP32-S3-EYE 固件。

## P0 目标（最小可用）

1. 板子上电，摄像头初始化
2. 每隔 N 分钟拍一张 JPG
3. 通过 WiFi 上传到服务器
4. 断网时存 MicroSD，恢复后补传

## 硬件

| 部件 | 规格 |
|---|---|
| 主控 | ESP32-S3-EYE（8MB PSRAM + 8MB Flash） |
| 摄像头 | OV2640（板载，定焦广角） |
| 补光 | 850nm 红外 LED ×2（待接） |
| 存储 | MicroSD 卡 |
| 联网 | WiFi 2.4GHz |

## 开发环境

待定（ESP-IDF 或 Arduino），确定后写在这里。

## 目录规划

```
firmware/
├── src/            # 源码
├── include/        # 头文件
├── platformio.ini  # 或 CMakeLists.txt
└── README.md
```

## 待办

- [ ] 确定开发框架
- [ ] 跑通摄像头拍照
- [ ] 跑通 WiFi 上传
- [ ] 加红外补光
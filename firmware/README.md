# firmware

ESP32-S3-EYE 固件（一期骨架）：白天定时抓拍 → 上传服务端 → 断网补传。

设计与验收见 `docs/specs/2026-11-11-shedding-alert-pipeline-design.md` §4。

## 一期行为

1. 上电 → 连 WiFi（STA）→ SNTP 对时。
2. **仅白天窗口抓拍**：本地时间 `[APP_CAPTURE_START_HOUR, APP_CAPTURE_END_HOUR)`（默认 08:00–20:00）内，每 `APP_CAPTURE_INTERVAL_MIN`（默认 30）分钟拍一张 640×480 JPEG。
3. 以 `multipart/form-data` 发 `POST /api/v1/images`，带 `X-Device-Id` 与 `X-Captured-At`（UTC ISO8601）。服务端收图后自动跑指标与状态判定，判定「正在蜕皮」会推送提醒（见服务端 README）。
4. 上传失败（或断网）→ 存入板载 SPIFFS 补传队列（最多 `APP_BACKLOG_MAX` 张，默认 7），每分钟重试，成功后删除。
5. 一期**只用可见光**，红外补光未接（无红外训练数据）；夜间不抓拍。

## 目录结构

```
firmware/
├── CMakeLists.txt          # ESP-IDF 工程入口
├── partitions.csv          # 8MB flash 分区（含 storage/SPIFFS 补传区）
├── sdkconfig.defaults      # 目标 esp32s3、8MB Octal PSRAM、自定义分区表
├── dependencies.lock       # 组件版本锁（esp32-camera 等）
└── main/
    ├── main.c              # 主循环：窗口判定、抓拍、上传/入队
    ├── app_config.h        # 编译期配置（WiFi/服务器/窗口/间隔/时区）
    ├── wifi.c / wifi.h     # STA 连接与自动重连
    ├── time_sync.c / .h    # SNTP 对时
    ├── camera.c / .h       # OV2640 初始化与抓帧（板载引脚）
    ├── uploader.c / .h     # multipart 上传
    └── backlog.c / .h      # SPIFFS 补传队列
```

## 构建与烧录

需要 ESP-IDF v5.4（本机已装在 `C:\Espressif\frameworks\esp-idf-v5.4.4`）。

```bash
# 在已激活 ESP-IDF 环境的终端里，于 firmware/ 目录执行
idf.py set-target esp32s3
idf.py build
idf.py -p <COM口> flash monitor
```

> 本机用 conhost 时 PowerShell 执行策略会挡 `export.ps1`，可改用 `export.bat`，并先把 IDF 自带的 python 与 git 加进 PATH（见 `.tmp/idf.bat` 的做法）。

## 配置

部署前必须改 `main/app_config.h` 里的占位值，或用 `-D` 覆盖：

| 宏 | 默认 | 说明 |
|---|---|---|
| `APP_WIFI_SSID` / `APP_WIFI_PASSWORD` | 占位 | WiFi 凭据 |
| `APP_SERVER_BASE_URL` | `http://192.168.1.100:8000` | 服务端根地址 |
| `APP_DEVICE_ID` | `gecko-eye-01` | 设备标识，须与服务端一致 |
| `APP_CAPTURE_START_HOUR` / `APP_CAPTURE_END_HOUR` | 8 / 20 | 抓拍窗口（本地时间） |
| `APP_CAPTURE_INTERVAL_MIN` | 30 | 抓拍间隔（分钟） |
| `APP_BACKLOG_MAX` | 7 | SPIFFS 补传队列上限 |
| `APP_TZ` | `CST-8` | POSIX 时区（Asia/Shanghai = UTC+8） |

```bash
idf.py -DAPP_WIFI_SSID='"my-ssid"' -DAPP_WIFI_PASSWORD='"my-pass"' \
       -DAPP_SERVER_BASE_URL='"http://192.168.1.50:8000"' build
```

## 摄像头引脚

ESP32-S3-EYE 板载 OV2640，引脚取自 `espressif/esp-bsp` 的 `esp32_s3_eye.h`：

| 信号 | GPIO | 信号 | GPIO |
|---|---|---|---|
| XCLK | 15 | PCLK | 13 |
| VSYNC | 6 | HREF | 7 |
| SCCB SDA | 4 | SCCB SCL | 5 |
| D0–D7 | 11 9 8 10 12 18 17 16 | PWDN / RESET | 未接 |

## 验证状态

- ✅ **编译通过**：ESP-IDF v5.4.4 + esp32-camera 2.1.x，target esp32s3，产物 `build/shedguard_eye.bin` 约 1.06 MB（app 分区 75% 空闲）。
- ⏳ **未上板实测**：手边无 ESP32-S3-EYE 实物，WiFi/相机/上传/补传均未在真机跑过；首次上板需重点验证相机初始化、XCLK 频率、抓拍窗口与补传。
- 未接红外补光；无 MicroSD 支持（补传走板载 SPIFFS，按一期规格）。

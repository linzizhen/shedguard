/*
 * 编译期配置。默认值只是占位，部署前必须改成真实值。
 * 每一项都可以用 -D 覆盖，例如：
 *   idf.py -DAPP_WIFI_SSID='"my-ssid"' -DAPP_WIFI_PASSWORD='"my-pass"' build
 * 或在 menuconfig 之外的 CMake 变量里注入。
 */
#pragma once

#ifndef APP_WIFI_SSID
#define APP_WIFI_SSID "your-wifi-ssid"
#endif

#ifndef APP_WIFI_PASSWORD
#define APP_WIFI_PASSWORD "your-wifi-password"
#endif

/* 服务端根地址，不含路径，例如 http://192.168.1.100:8000 */
#ifndef APP_SERVER_BASE_URL
#define APP_SERVER_BASE_URL "http://192.168.1.100:8000"
#endif

/* 设备标识，与服务端 images/device_id 一致 */
#ifndef APP_DEVICE_ID
#define APP_DEVICE_ID "gecko-eye-01"
#endif

/* 抓拍窗口：本地时间 [START, END) 小时之间，每 INTERVAL 分钟一张 */
#ifndef APP_CAPTURE_START_HOUR
#define APP_CAPTURE_START_HOUR 8
#endif

#ifndef APP_CAPTURE_END_HOUR
#define APP_CAPTURE_END_HOUR 20
#endif

#ifndef APP_CAPTURE_INTERVAL_MIN
#define APP_CAPTURE_INTERVAL_MIN 30
#endif

/* SPIFFS 补传队列最多保留的图片张数 */
#ifndef APP_BACKLOG_MAX
#define APP_BACKLOG_MAX 7
#endif

/* 时区字符串（POSIX TZ）。Asia/Shanghai = UTC+8 -> "CST-8" */
#ifndef APP_TZ
#define APP_TZ "CST-8"
#endif

/* JPEG 质量：0-63，越小越清晰、体积越大 */
#define APP_IMAGE_QUALITY 12

/* 单次 HTTP 上传超时 */
#define APP_HTTP_TIMEOUT_MS 15000

/* 主循环节拍 */
#define APP_LOOP_INTERVAL_MS 30000
/* 补传队列重试间隔 */
#define APP_BACKLOG_RETRY_MS 60000

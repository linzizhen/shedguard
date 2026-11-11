#pragma once

#include <stddef.h>
#include <time.h>

#include "esp_err.h"

/* 上传一张 JPEG 到 service：POST /api/v1/images（multipart），
 * 带 X-Device-Id 与 X-Captured-At 头。返回 ESP_OK 表示服务端 2xx。 */
esp_err_t uploader_send(const unsigned char *jpeg, size_t len, time_t captured_at);

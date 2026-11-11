#pragma once

#include <stdbool.h>
#include "esp_err.h"

/* 初始化 STA 并阻塞等待拿到 IP，超时返回 ESP_ERR_TIMEOUT。 */
esp_err_t wifi_connect_blocking(int timeout_ms);

/* 当前是否已连上（拿到 IP）。 */
bool wifi_is_connected(void);

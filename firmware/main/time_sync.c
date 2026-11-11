#include "time_sync.h"

#include <sys/time.h>

#include "esp_log.h"
#include "esp_sntp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "time_sync";

/* 用一个明显晚于固件编译时间的阈值判断「时间是否已校准」 */
#define TIME_VALID_THRESHOLD 1700000000 /* 2023-11-14 */

void time_sync_init(void)
{
    esp_sntp_setoperatingmode(ESP_SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_setservername(1, "ntp.aliyun.com");
    esp_sntp_init();
}

bool time_sync_wait(int timeout_ms)
{
    const TickType_t step = pdMS_TO_TICKS(200);
    int waited = 0;
    while (time(NULL) < TIME_VALID_THRESHOLD) {
        if (waited >= timeout_ms) {
            ESP_LOGE(TAG, "等待 NTP 对时超时");
            return false;
        }
        vTaskDelay(step);
        waited += 200;
    }
    ESP_LOGI(TAG, "时间已校准，UTC=%lld", (long long)time(NULL));
    return true;
}

time_t time_now_utc(void)
{
    return time(NULL);
}

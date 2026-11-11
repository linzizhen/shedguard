#include <stdbool.h>
#include <stdlib.h>
#include <time.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "app_config.h"
#include "backlog.h"
#include "camera.h"
#include "time_sync.h"
#include "uploader.h"
#include "wifi.h"

static const char *TAG = "shedguard";

/* 抓一帧并上传；上传失败（或无网络）则入补传队列。 */
static void capture_and_upload(void)
{
    camera_fb_t *fb = NULL;
    if (camera_capture(&fb) != ESP_OK) {
        return;
    }

    time_t now = time(NULL);
    esp_err_t err = ESP_FAIL;
    if (wifi_is_connected()) {
        err = uploader_send(fb->buf, fb->len, now);
    }
    if (err != ESP_OK) {
        if (backlog_store(fb->buf, fb->len, now) == ESP_OK) {
            ESP_LOGW(TAG, "上传失败，已存入补传队列（%d 张）", backlog_count());
        }
    }
    camera_return(fb);
}

static void init_nvs(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
}

void app_main(void)
{
    ESP_LOGI(TAG, "shedguard 固件启动，设备 %s", APP_DEVICE_ID);

    setenv("TZ", APP_TZ, 1);
    tzset();

    init_nvs();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    if (backlog_init() != ESP_OK) {
        ESP_LOGE(TAG, "补传队列不可用，将继续运行但断网时图片会丢失");
    }

    if (wifi_connect_blocking(20000) == ESP_OK) {
        time_sync_init();
        if (!time_sync_wait(15000)) {
            ESP_LOGW(TAG, "未能对时，抓拍窗口可能不准");
        }
        backlog_flush();
    } else {
        ESP_LOGE(TAG, "首次 WiFi 连接失败，稍后由自动重连恢复");
    }

    if (camera_init() != ESP_OK) {
        ESP_LOGE(TAG, "相机不可用，仅执行补传");
    }

    ESP_LOGI(TAG, "进入主循环：窗口 %02d:00-%02d:00，每 %d 分钟抓拍",
             APP_CAPTURE_START_HOUR, APP_CAPTURE_END_HOUR, APP_CAPTURE_INTERVAL_MIN);

    time_t last_capture = 0;
    int64_t last_flush_ms = 0;

    for (;;) {
        time_t now = time(NULL);
        struct tm local;
        localtime_r(&now, &local);

        bool in_window = local.tm_hour >= APP_CAPTURE_START_HOUR &&
                         local.tm_hour < APP_CAPTURE_END_HOUR;
        bool due = (last_capture == 0) ||
                   (now - last_capture >= (time_t)APP_CAPTURE_INTERVAL_MIN * 60);

        if (in_window && due) {
            ESP_LOGI(TAG, "定时抓拍（%02d:%02d）", local.tm_hour, local.tm_min);
            capture_and_upload();
            last_capture = now;
        }

        int64_t now_ms = esp_timer_get_time() / 1000;
        if (wifi_is_connected() && (now_ms - last_flush_ms) >= APP_BACKLOG_RETRY_MS) {
            backlog_flush();
            last_flush_ms = now_ms;
        }

        vTaskDelay(pdMS_TO_TICKS(APP_LOOP_INTERVAL_MS));
    }
}

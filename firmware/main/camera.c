#include "camera.h"

#include "esp_log.h"
#include "driver/ledc.h"

#include "app_config.h"

static const char *TAG = "camera";

/*
 * ESP32-S3-EYE（OV2640）板载引脚，取自 espressif/esp-bsp 的
 * bsp/esp32_s3_eye/include/bsp/esp32_s3_eye.h 与 BSP_I2C_SDA/SCL：
 *   XCLK=15 PCLK=13 VSYNC=6 HREF=7
 *   D0..D7 = 11 9 8 10 12 18 17 16
 *   SCCB SDA=4 SCL=5  PWDN/RESET 未接
 */
static camera_config_t make_config(void)
{
    camera_config_t cfg = {
        .pin_pwdn = -1,
        .pin_reset = -1,
        .pin_xclk = 15,
        .pin_sccb_sda = 4,
        .pin_sccb_scl = 5,
        .pin_d7 = 16,
        .pin_d6 = 17,
        .pin_d5 = 18,
        .pin_d4 = 12,
        .pin_d3 = 10,
        .pin_d2 = 8,
        .pin_d1 = 9,
        .pin_d0 = 11,
        .pin_vsync = 6,
        .pin_href = 7,
        .pin_pclk = 13,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = FRAMESIZE_VGA,
        .jpeg_quality = APP_IMAGE_QUALITY,
        .fb_count = 2,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
        .sccb_i2c_port = -1,
    };
    return cfg;
}

esp_err_t camera_init(void)
{
    camera_config_t cfg = make_config();
    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "相机初始化失败: %s", esp_err_to_name(err));
        return err;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor != NULL) {
        sensor->set_vflip(sensor, 1);
        sensor->set_hmirror(sensor, 0);
    }
    ESP_LOGI(TAG, "相机就绪（VGA / JPEG）");
    return ESP_OK;
}

esp_err_t camera_capture(camera_fb_t **fb)
{
    *fb = esp_camera_fb_get();
    if (*fb == NULL) {
        ESP_LOGE(TAG, "抓帧失败");
        return ESP_FAIL;
    }
    return ESP_OK;
}

void camera_return(camera_fb_t *fb)
{
    if (fb != NULL) {
        esp_camera_fb_return(fb);
    }
}

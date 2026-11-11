#pragma once

#include "esp_camera.h"
#include "esp_err.h"

/* 初始化 OV2640（ESP32-S3-EYE 板载引脚，帧缓冲放 PSRAM）。 */
esp_err_t camera_init(void);

/* 抓一帧 JPEG。成功后 *fb 需用 camera_return 归还。 */
esp_err_t camera_capture(camera_fb_t **fb);

/* 归还帧缓冲。 */
void camera_return(camera_fb_t *fb);

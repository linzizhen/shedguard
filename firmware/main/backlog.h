#pragma once

#include <stddef.h>
#include <time.h>

#include "esp_err.h"

/* 挂载 SPIFFS 补传分区（label=storage，挂到 /spiffs）。 */
esp_err_t backlog_init(void);

/* 当前队列里的图片张数。 */
int backlog_count(void);

/* 入队一张图（失败时保留，供后续补传）。超过上限会丢弃最旧的一张。 */
esp_err_t backlog_store(const unsigned char *data, size_t len, time_t captured_at);

/* 依次尝试补传队列中的图片，成功即删除；遇到失败则停下等下次。 */
void backlog_flush(void);

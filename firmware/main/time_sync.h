#pragma once

#include <stdbool.h>
#include <time.h>

/* 启动 SNTP 轮询。须在已连网后调用。 */
void time_sync_init(void);

/* 阻塞等待系统时间被校准，超时返回 false。 */
bool time_sync_wait(int timeout_ms);

/* 当前 UTC 时间（秒）。未校准时返回 0 附近的极小值。 */
time_t time_now_utc(void);

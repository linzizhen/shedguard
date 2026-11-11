#include "uploader.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_http_client.h"
#include "esp_log.h"

#include "app_config.h"

static const char *TAG = "uploader";

static const char *BOUNDARY = "----shedguardBoundary7MA4YWxkTrZu0gW";

esp_err_t uploader_send(const unsigned char *jpeg, size_t len, time_t captured_at)
{
    char captured_iso[32];
    struct tm tm_utc;
    gmtime_r(&captured_at, &tm_utc);
    strftime(captured_iso, sizeof(captured_iso), "%Y-%m-%dT%H:%M:%SZ", &tm_utc);

    char head[320];
    int head_len = snprintf(head, sizeof(head),
                            "--%s\r\n"
                            "Content-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\n"
                            "Content-Type: image/jpeg\r\n\r\n",
                            BOUNDARY);
    if (head_len <= 0 || head_len >= (int)sizeof(head)) {
        return ESP_FAIL;
    }

    char tail[96];
    int tail_len = snprintf(tail, sizeof(tail), "\r\n--%s--\r\n", BOUNDARY);
    if (tail_len <= 0 || tail_len >= (int)sizeof(tail)) {
        return ESP_FAIL;
    }

    size_t total = (size_t)head_len + len + (size_t)tail_len;
    unsigned char *body = (unsigned char *)malloc(total);
    if (body == NULL) {
        ESP_LOGE(TAG, "分配 multipart 缓冲失败 (%u 字节)", (unsigned)total);
        return ESP_ERR_NO_MEM;
    }
    memcpy(body, head, (size_t)head_len);
    memcpy(body + head_len, jpeg, len);
    memcpy(body + head_len + len, tail, (size_t)tail_len);

    char url[192];
    snprintf(url, sizeof(url), "%s/api/v1/images", APP_SERVER_BASE_URL);

    char content_type[128];
    snprintf(content_type, sizeof(content_type), "multipart/form-data; boundary=%s", BOUNDARY);

    esp_http_client_config_t cfg = {
        .url = url,
        .timeout_ms = APP_HTTP_TIMEOUT_MS,
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (client == NULL) {
        free(body);
        return ESP_FAIL;
    }

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", content_type);
    esp_http_client_set_header(client, "X-Device-Id", APP_DEVICE_ID);
    esp_http_client_set_header(client, "X-Captured-At", captured_iso);
    esp_http_client_set_post_field(client, (const char *)body, (int)total);

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);

    esp_http_client_cleanup(client);
    free(body);

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "HTTP 请求失败: %s", esp_err_to_name(err));
        return err;
    }
    if (status != 200 && status != 201) {
        ESP_LOGW(TAG, "服务端返回 %d", status);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "上传成功 %u 字节 (%s)", (unsigned)len, captured_iso);
    return ESP_OK;
}

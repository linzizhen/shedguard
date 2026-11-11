#include "backlog.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "esp_log.h"
#include "esp_spiffs.h"

#include "app_config.h"
#include "uploader.h"

static const char *TAG = "backlog";

#define BACKLOG_DIR "/spiffs"
#define NAME_PREFIX "q_"

static void path_for(char *out, size_t out_len, time_t captured_at)
{
    snprintf(out, out_len, BACKLOG_DIR "/" NAME_PREFIX "%lld.jpg", (long long)captured_at);
}

/* 若文件名形如 q_<epoch>.jpg，解析并返回 true */
static bool parse_name(const char *name, time_t *epoch_out)
{
    if (strncmp(name, NAME_PREFIX, strlen(NAME_PREFIX)) != 0) {
        return false;
    }
    long long v = 0;
    if (sscanf(name + strlen(NAME_PREFIX), "%lld.jpg", &v) != 1) {
        return false;
    }
    *epoch_out = (time_t)v;
    return true;
}

esp_err_t backlog_init(void)
{
    esp_vfs_spiffs_conf_t conf = {
        .base_path = BACKLOG_DIR,
        .partition_label = "storage",
        .max_files = 4,
        .format_if_mount_failed = true,
    };
    esp_err_t err = esp_vfs_spiffs_register(&conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SPIFFS 挂载失败: %s", esp_err_to_name(err));
        return err;
    }
    size_t total = 0, used = 0;
    esp_spiffs_info("storage", &total, &used);
    ESP_LOGI(TAG, "SPIFFS 就绪：%u/%u 字节，队列 %d 张", (unsigned)used, (unsigned)total,
             backlog_count());
    return ESP_OK;
}

int backlog_count(void)
{
    DIR *dir = opendir(BACKLOG_DIR);
    if (dir == NULL) {
        return 0;
    }
    int n = 0;
    struct dirent *ent;
    time_t epoch;
    while ((ent = readdir(dir)) != NULL) {
        if (parse_name(ent->d_name, &epoch)) {
            n++;
        }
    }
    closedir(dir);
    return n;
}

/* 找到最旧的一张，填 full_path 与 epoch；没有则返回 false */
static bool find_oldest(char *full_path, size_t path_len, time_t *epoch_out)
{
    DIR *dir = opendir(BACKLOG_DIR);
    if (dir == NULL) {
        return false;
    }
    bool found = false;
    time_t best = 0;
    char best_name[64] = { 0 };
    struct dirent *ent;
    time_t epoch;
    while ((ent = readdir(dir)) != NULL) {
        if (!parse_name(ent->d_name, &epoch)) {
            continue;
        }
        if (!found || epoch < best) {
            found = true;
            best = epoch;
            strlcpy(best_name, ent->d_name, sizeof(best_name));
        }
    }
    closedir(dir);
    if (!found) {
        return false;
    }
    snprintf(full_path, path_len, BACKLOG_DIR "/%s", best_name);
    *epoch_out = best;
    return true;
}

esp_err_t backlog_store(const unsigned char *data, size_t len, time_t captured_at)
{
    /* 队列满则删最旧 */
    while (backlog_count() >= APP_BACKLOG_MAX) {
        char oldest_path[96];
        time_t oldest_epoch;
        if (!find_oldest(oldest_path, sizeof(oldest_path), &oldest_epoch)) {
            break;
        }
        ESP_LOGW(TAG, "队列已满，丢弃最旧 %s", oldest_path);
        unlink(oldest_path);
    }

    char path[96];
    path_for(path, sizeof(path), captured_at);
    FILE *f = fopen(path, "wb");
    if (f == NULL) {
        ESP_LOGE(TAG, "写入补传文件失败: %s", path);
        return ESP_FAIL;
    }
    size_t written = fwrite(data, 1, len, f);
    fclose(f);
    if (written != len) {
        ESP_LOGE(TAG, "补传文件写入不完整 (%u/%u)", (unsigned)written, (unsigned)len);
        unlink(path);
        return ESP_FAIL;
    }
    ESP_LOGW(TAG, "已入补传队列: %s（当前 %d 张）", path, backlog_count());
    return ESP_OK;
}

void backlog_flush(void)
{
    for (int guard = 0; guard < APP_BACKLOG_MAX + 2; guard++) {
        char path[96];
        time_t epoch;
        if (!find_oldest(path, sizeof(path), &epoch)) {
            return;
        }

        struct stat st;
        if (stat(path, &st) != 0 || st.st_size <= 0) {
            unlink(path);
            continue;
        }

        unsigned char *buf = (unsigned char *)malloc((size_t)st.st_size);
        if (buf == NULL) {
            ESP_LOGE(TAG, "补传分配失败 %u 字节", (unsigned)st.st_size);
            return;
        }
        FILE *f = fopen(path, "rb");
        if (f == NULL) {
            free(buf);
            return;
        }
        size_t got = fread(buf, 1, (size_t)st.st_size, f);
        fclose(f);
        if (got != (size_t)st.st_size) {
            ESP_LOGW(TAG, "补传文件读取不完整，先保留: %s", path);
            free(buf);
            return;
        }

        esp_err_t err = uploader_send(buf, got, epoch);
        free(buf);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "补传失败，保留 %s 稍后重试", path);
            return;
        }
        unlink(path);
        ESP_LOGI(TAG, "补传成功并删除 %s", path);
    }
}

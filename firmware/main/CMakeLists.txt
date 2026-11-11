idf_component_register(
    SRCS "main.c" "wifi.c" "time_sync.c" "camera.c" "uploader.c" "backlog.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_http_client esp_netif esp_event nvs_flash esp_timer spiffs
)

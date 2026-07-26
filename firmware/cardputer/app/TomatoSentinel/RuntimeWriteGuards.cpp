#include <esp_err.h>
#include <esp_flash.h>
#include <esp_partition.h>

// Arduino-ESP32 normally confirms pending OTA images and initializes NVS
// before setup(). This proof of concept defers OTA confirmation and replaces
// NVS initialization at link time so the framework cannot format NVS during
// the first hardware validation.
extern "C" bool verifyRollbackLater() {
  return true;
}

extern "C" esp_err_t __wrap_nvs_flash_init() {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_partition_write(
    const esp_partition_t*, size_t, const void*, size_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_partition_write_raw(
    const esp_partition_t*, size_t, const void*, size_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_partition_erase_range(
    const esp_partition_t*, size_t, size_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_flash_write(
    esp_flash_t*, const void*, uint32_t, uint32_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_flash_write_encrypted(
    esp_flash_t*, uint32_t, const void*, uint32_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t __wrap_esp_flash_erase_region(
    esp_flash_t*, uint32_t, uint32_t) {
  return ESP_ERR_NOT_SUPPORTED;
}

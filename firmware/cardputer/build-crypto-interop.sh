#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: firmware/cardputer/build-crypto-interop.sh <build-directory>" >&2
  exit 2
fi

build_directory=$1
if [[ -z "$build_directory" || "$build_directory" == "/" ]]; then
  echo "refusing unsafe build directory" >&2
  exit 2
fi

arduino_cli=${TOMATO_ARDUINO_CLI:-arduino-cli}
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
sketch_directory="$repository_root/firmware/cardputer/app/TomatoSentinel"
config_file="$repository_root/firmware/cardputer/arduino-cli.yaml"

mkdir -p -- "$build_directory"

export SOURCE_DATE_EPOCH=0

# Compile-only evidence artifact. This entry point intentionally contains no
# upload command and marks the resulting image as ineligible for deployment.
exec "$arduino_cli" \
  --config-file "$config_file" \
  compile \
  --profile original \
  --build-property \
  "compiler.cpp.extra_flags=-DTOMATO_TARGET_CARDPUTER_ORIGINAL=1 \
-DTOMATO_RUNTIME_WRITE_GUARDS=1 \
-DTOMATO_CRYPTO_INTEROP_SELF_TEST=1 \
-DTOMATO_LOCAL_FRAME_INTEROP_SELF_TEST=1 \
-DTOMATO_INTEROP_NON_DEPLOYABLE=1 \
-DNO_GLOBAL_SERIAL \
-DSerial=HWCDCSerial" \
  --build-property \
  "compiler.c.elf.extra_flags=-Wl,--wrap=nvs_flash_init \
-Wl,--wrap=esp_partition_write \
-Wl,--wrap=esp_partition_write_raw \
-Wl,--wrap=esp_partition_erase_range \
-Wl,--wrap=esp_flash_write \
-Wl,--wrap=esp_flash_write_encrypted \
-Wl,--wrap=esp_flash_erase_region" \
  --build-path "$build_directory" \
  "$sketch_directory"

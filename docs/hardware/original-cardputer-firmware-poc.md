# Original Cardputer firmware proof of concept

- Execution date: 2026-07-25; safety rebuild: 2026-07-26
  (America/Sao_Paulo)
- Result: compile-only proof accepted
- Hardware upload: not performed
- Physical hardware validation: not performed

## Objective and boundary

The proof of concept builds one bounded local interface for the original
M5Stack Cardputer. It displays the `ASSISTANT` profile, verifies the explicit
original-board build profile and samples G0 as the physical cancellation
button. The exact physical model is a mandatory human preflight check.

This behavior is local and read-only (`R0`). It does not require an operator
role, resource grant, operation scope or confirmation because it executes no
remote or state-changing tool. It reads and displays no personal or credential
data.

Wi-Fi, BLE, keyboard, microphone, speaker, IMU, RTC, SD card, infrared, Grove
and external modules are unused and not initialized.

## Upstream intake result

| Project | Needed part | Mode | Result |
| --- | --- | --- | --- |
| Arduino CLI 1.5.1 | dependency resolution and compilation | `native_library` build tool | approved |
| Arduino-ESP32 3.3.10 | ESP32-S3 framework | `native_library` | approved |
| M5Unified 0.2.19 | broad board initialization candidate | `reference_only` | rejected after exact-source review |
| M5GFX 0.2.26 | fixed LovyanGFX display primitives | `native_library` | approved without automatic detection |
| M5Cardputer 1.2.0 | keyboard convenience API | `reference_only` | rejected |
| M5Cardputer UserDemo V0.9 | original display configuration | `reference_only` | approved reference; not executed |
| Bruce 1.16 | UI and board-architecture comparison | `reference_only` | rejected; source observations only |
| Evil-M5Project | UI and startup comparison | `reference_only` | rejected; unlicensed and contains R3 behavior |
| M5Launcher 2.7.2 | image-validation and recovery comparison | `reference_only` | rejected; state-changing flash manager |
| PlatformIO Core 6.1.19 | build-tool candidate | `reference_only` | not selected |
| platform-espressif32 6.7.0 | documented manufacturer example | `reference_only` | rejected |

No upstream application source was copied. The implementation independently
defines only the ST7789 wiring and geometry documented by the original
Cardputer schematic; the exact UserDemo V0.9 source corroborated those values.
All entries, exact commits, licenses, review notes and removal status are in
the upstream software catalog. The focused community-source comparison is in
`docs/hardware/cardputer-community-project-review.md`.

### Safety correction from exact-source review

The first compile-only image is revoked and must not be flashed. M5Unified
0.2.19 sets GPIO46 high as an output before it knows which ESP32-S3 board is
running. On the original Cardputer, GPIO46 is connected to the SPM1423
microphone DATA output and is also an ESP32-S3 strapping pin. The configured
`internal_mic=false` did not restore it to input.

M5GFX automatic detection was also removed because it can probe unrelated
board pins and cache the result in NVS. The replacement uses a fixed display
object with only:

- MOSI 35, SCLK 36, DC 34, CS 37 and reset 33;
- backlight PWM 38, held at zero through initialization and then limited to
  64/255;
- GPIO0 as an input, relying on the original board's external 10 kOhm pull-up;
- GPIO46 explicitly as an input.

The side switch physically controls the original Cardputer's 5 V output path.
M5Unified's `output_power=false` was not an effective control for this board
and is no longer claimed as one.

## Primary sources reviewed

- [M5Stack original Cardputer product documentation][cardputer-docs], including
  the ESP32-S3FN8/8 MB identity, pin map, power-switch instructions and
  original schematics;
- [original Cardputer main schematic][cardputer-schematic],
  [base schematic][cardputer-base-schematic] and
  [Stamp-S3 schematic][stamps3-schematic];
- [M5Stack Arduino upload procedure][m5-arduino-upload] and
  [factory restore procedure][m5-factory-restore];
- exact [M5Unified 0.2.19 initialization source][m5unified-gpio46];
- exact [M5GFX 0.2.26 Cardputer detection source][m5gfx-detection];
- exact [official M5Cardputer UserDemo V0.9 display configuration][userdemo-display];
- Espressif's [ESP32-S3 boot-mode guidance][espressif-boot] and
  [esptool flashing guidance][espressif-flashing].

The manufacturer projects were inspected as sources, not executed. The
UserDemo's hard-coded port/flash script, bundled binaries and broad component
tree were explicitly not adopted. The M5Cardputer library delegates startup
to M5Unified and therefore does not remove the GPIO46 concern.

## Commands executed

The Arduino CLI archive was downloaded directly from the official GitHub
release. It was not piped to a shell. Its SHA-256 was checked before extraction:

```text
sha256sum /tmp/arduino-cli_1.5.1_Linux_64bit.tar.gz
```

Observed checksum:

```text
28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b
```

The positive build used isolated data, download, user and build directories
through the compile-only safe entry point:

```text
firmware/cardputer/build-safe.sh <temporary-build-directory>
```

The safe entry point fixes `SOURCE_DATE_EPOCH=0`. This removes the sketch
compile clock from the flashable image. Arduino-ESP32 still embeds a 32-byte
hash of the full ELF, including non-flash debug metadata; that value causes
the application checksum and final image hash to differ between temporary
build directories. Two clean builds were otherwise byte-identical: the only
65 differing bytes were that ELF hash, the derived one-byte checksum and the
derived 32-byte image hash. Artifact approval therefore uses one exact
selected binary plus this bounded semantic comparison, rather than falsely
claiming whole-file reproducibility.

Result:

```text
Sketch uses 346763 bytes (10%) of program storage space.
Global variables use 22412 bytes (6%) of dynamic memory.
```

The previously reviewed application binary was 346,912 bytes:

```text
SHA-256 8af992756dce03a77aa8cbec8e1364ab2e09d25fe3ffcc0fe44df6503bee3068
```

A clean post-preflight build with fixed compile time produced the selected
candidate with the same size and executable content:

```text
SHA-256 c7d1b51ec65de4f43429568bb6407b9c124ec5a697ba5ecb58b65c7a58fc0cdd
```

The original generic-target build was discarded after the physical-flashing
safety review. A new clean build used the board-specific
`esp32:esp32:m5stack_cardputer` target with 8 MB flash, no PSRAM, 115200 baud
and full-flash erase disabled. Offline image inspection reported ESP32-S3,
8 MB, DIO at 80 MHz and valid checksums for both bootloader and application.
This is compile-time and artifact evidence, not yet physical validation.
Final-symbol inspection found no M5Unified, M5GFX automatic-detection or
Cardputer-ADV-detection symbol in the linked ELF. Every reachable public
NVS-initialization, partition-write/erase and raw-flash-write/erase call was
resolved to a fail-closed wrapper returning `ESP_ERR_NOT_SUPPORTED`.
Arduino's pre-setup OTA verification hook resolves to the local deferral
override.
The build also contains hardware CDC/JTAG logging only. `HWCDCSerial` is
present, while `Serial0`, `HardwareSerial::begin`, `HardwareSerial::setPins`
and `uartBegin` are absent. GPIO43/44 are therefore not assigned to UART0 by
the candidate application.
The word `board_M5CardputerADV` exists only in ELF debug information supplied
by the M5GFX dependency; it is absent from the flashable application binary
and has no corresponding linked detection symbol.

## Negative control

The same compile was executed without
`TOMATO_TARGET_CARDPUTER_ORIGINAL=1`. It failed as required:

```text
error: #error "Build refused: select the explicit original Cardputer target"
```

The compile was also executed with the target marker but a generic
`esp32:esp32:esp32s3` FQBN. It failed independently:

```text
error: #error "Build refused: select esp32:esp32:m5stack_cardputer"
```

An exact-board build without the independent runtime-write-guard marker also
failed:

```text
error: #error "Build refused: runtime flash-write guards are mandatory"
```

A build with USB-OTG/default CDC instead of hardware CDC/JTAG failed:

```text
error: #error "Build refused: select hardware USB CDC/JTAG logging"
```

The negative builds themselves did not access hardware. Subsequent read-only
physical preflight accessed the original Cardputer through its ESP32-S3 ROM
bootloader with `--no-stub`, confirmed the hardware and security state, and
created a private complete flash backup. After a separate exact R2 approval,
only the selected application image was uploaded to the verified `app0`
offset; generated bootloader, partition-table and `boot_app0` images were not
uploaded.

## Flashing safety review

The generated upload layout contains four separate images:

| Offset | Image | Size | SHA-256 |
| --- | --- | ---: | --- |
| `0x0000` | bootloader | 19,984 bytes | `3a06e81d78e928687d7acd8abcd069543a4413de4398e2e2940a97b3fc739fd8` |
| `0x8000` | partition table | 3,072 bytes | `1d9cca96de0fe07ad7fc0648b9878ddecd9ce565e38b589ad20fea698ed4c80c` |
| `0xe000` | `boot_app0` | 8,192 bytes | `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` |
| `0x10000` | selected application | 346,912 bytes | `c7d1b51ec65de4f43429568bb6407b9c124ec5a697ba5ecb58b65c7a58fc0cdd` |

Arduino-ESP32's `FlashMode=qio` board option deliberately resolves
`build.boot=qio` while its initial image header and esptool write argument
remain DIO at 80 MHz. The inspected `flash_args` therefore says
`--flash-mode dio`; this matches the pinned platform definition and is not an
unresolved mismatch.

This generated layout is not an approved write plan. It differs from both the
official UserDemo V0.9 layout and the connected device's verified layout. The
device has one 3 MB `app0` partition at `0x10000`; generated bootloader,
partition-table and `boot_app0` images must not replace its existing regions.
The fail-safe design, exact physical procedure, read-only preflight, backup
requirement and prohibited commands are documented in
`docs/hardware/cardputer-fail-safe-mode.md` and
`docs/hardware/original-cardputer-flashing-safety.md`.

## Resource observations

The isolated Arduino installation consumed approximately:

- 5.6 GB for installed platform data;
- 1.6 GB for downloaded archives;
- 102 MB for the positive build directory.

Arduino-ESP32 3.3.10 installs tools and libraries for the full ESP32 family,
not only ESP32-S3. A hosted CI compile should not be enabled until caching,
download integrity and storage/time limits are designed; ordinary CI already
checks the static firmware contract without network access.

## Physical application evidence and remaining acceptance

Read-only hardware identity and flash-layout acceptance completed. The first
application-only write passed built-in and independent digest verification.
The operator then confirmed:

1. the expected ready UI on the original Cardputer;
2. readable display orientation and visible `ASSISTANT` profile;
3. G0 changed the UI to the expected cancel-requested safe state;
4. a manual Reset returned to ready state without entering fail-safe mode;
5. no abnormal heat, odor, flicker or repeated resets during the observed
   USB-powered test.

This does not replace instrumented current or thermal measurement. Operation
from the batteries with the side switch in `ON`, deliberate watchdog/panic
recovery and longer-duration soak testing remain unverified.

Microphone, keyboard, transport, device identity, signed firmware, secure boot
and update rollback protection remain separate implementation stages.

[cardputer-docs]: https://docs.m5stack.com/en/core/Cardputer
[cardputer-schematic]: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/481/Sch_M5Cardputer.pdf
[cardputer-base-schematic]: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/481/Sch_M5cardputer_Base.pdf
[stamps3-schematic]: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/522/Sch_M5StampS3_v0.2.pdf
[m5-arduino-upload]: https://docs.m5stack.com/en/arduino/m5cardputer/program
[m5-factory-restore]: https://docs.m5stack.com/en/guide/restore_factory/cardputer
[m5unified-gpio46]: https://github.com/m5stack/M5Unified/blob/4fb444784c85791e0b0207701392b42be234b2e7/src/M5Unified.hpp#L347-L348
[m5gfx-detection]: https://github.com/m5stack/M5GFX/blob/729297d6e3d657ddc1ec5189bac2f2ea68828085/src/M5GFX.cpp#L2290-L2395
[userdemo-display]: https://github.com/m5stack/M5Cardputer-UserDemo/blob/b0c678d5f19d9c2c6d7c362a1a478369994cadc6/main/hal/display/hal_display.hpp
[espressif-boot]: https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html
[espressif-flashing]: https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/flashing-firmware.html

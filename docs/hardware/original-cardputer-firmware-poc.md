# Original Cardputer firmware proof of concept

- Execution date: 2026-07-25 (America/Sao_Paulo)
- Result: compile-only proof accepted
- Hardware upload: not performed
- Physical hardware validation: not performed

## Objective and boundary

The proof of concept builds one bounded local interface for the original
M5Stack Cardputer. It displays the `ASSISTANT` profile, verifies the detected
board and samples G0 as the physical cancellation button.

This behavior is local and read-only (`R0`). It does not require an operator
role, resource grant, operation scope or confirmation because it executes no
remote or state-changing tool. It reads and displays no personal or credential
data.

Wi-Fi, BLE, keyboard, microphone, speaker, IMU, RTC, SD card, infrared and
external modules are disabled or unused.

## Upstream intake result

| Project | Needed part | Mode | Result |
| --- | --- | --- | --- |
| Arduino CLI 1.5.1 | dependency resolution and compilation | `native_library` build tool | approved |
| Arduino-ESP32 3.3.10 | ESP32-S3 framework | `native_library` | approved |
| M5Unified 0.2.19 | display, board detection and G0 | `native_library` | approved |
| M5GFX 0.2.26 | display driver | `native_library` | approved |
| M5Cardputer 1.2.0 | keyboard convenience API | `reference_only` | rejected |
| PlatformIO Core 6.1.19 | build-tool candidate | `reference_only` | not selected |
| platform-espressif32 6.7.0 | documented manufacturer example | `reference_only` | rejected |

No M5Cardputer source was copied. Standard M5Unified APIs provide the initial
display, board-detection and G0 behavior without its unrelated dependencies.
All entries, exact commits, licenses, review notes and removal status are in
the upstream software catalog.

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

The positive build used isolated data, download, user and build directories:

```text
arduino-cli --config-file firmware/cardputer/arduino-cli.yaml \
  compile --profile original \
  --build-property \
  build.extra_flags=-DTOMATO_TARGET_CARDPUTER_ORIGINAL=1 \
  --build-path <temporary-build-directory> \
  firmware/cardputer/app/TomatoSentinel
```

Result:

```text
Sketch uses 506019 bytes (15%) of program storage space.
Global variables use 25012 bytes (7%) of dynamic memory.
```

The produced application binary was 506,160 bytes:

```text
SHA-256 c3193dd61f7f65ef434f28da41687752921e32bd9c61ad600c4c0aea9690a50b
```

A repeated clean build after a host crash produced the same binary checksum.
This is useful reproducibility evidence for the same host environment, not yet
a cross-platform reproducible-build guarantee.

## Negative control

The same compile was executed without
`TOMATO_TARGET_CARDPUTER_ORIGINAL=1`. It failed as required:

```text
error: #error "Build refused: select the explicit original Cardputer target"
```

No firmware was uploaded and no serial or USB device was accessed.

## Resource observations

The isolated Arduino installation consumed approximately:

- 5.6 GB for installed platform data;
- 1.6 GB for downloaded archives;
- 102 MB for the positive build directory.

Arduino-ESP32 3.3.10 installs tools and libraries for the full ESP32 family,
not only ESP32-S3. A hosted CI compile should not be enabled until caching,
download integrity and storage/time limits are designed; ordinary CI already
checks the static firmware contract without network access.

## Physical acceptance still required

An original Cardputer must verify:

1. correct board detection and rejection behavior;
2. display orientation, readability and persistent profile indicator;
3. G0 responsiveness and priority during ordinary UI work;
4. reboot behavior and absence of silent profile changes;
5. power behavior with external output, audio, IMU and RTC disabled.

Microphone, keyboard, transport, device identity, signed firmware, secure boot
and update rollback protection remain separate implementation stages.

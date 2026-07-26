# ADR-0005: Original Cardputer firmware toolchain

- Status: Accepted
- Date: 2026-07-25
- Safety revision: 2026-07-26

## Context

The first physical target is the original M5Stack Cardputer, not Cardputer
Adv. The repository needs a reproducible firmware build before microphone,
keyboard or transport work begins. The first image must prove only a narrow
boundary: explicit board selection, a permanently visible operating profile
and physical cancellation through G0.

Manufacturer documentation presents Arduino IDE, ESP-IDF and PlatformIO as
supported approaches. Its PlatformIO example selects Espressif platform 6.7.0,
which pins Arduino-ESP32 2.0.16. That framework version falls inside several
published vulnerability ranges fixed in 3.3.8 or later.

The separate M5Cardputer library package was also evaluated. Release 1.2.0 has
no repository-level license, declares library version 1.1.1, has no test suite
and pulls IRremote and LibSSH-ESP32 even though the initial firmware needs
neither. This rejection does not apply to the board-specific
`m5stack_cardputer` target already shipped in Arduino-ESP32.

An exact-source review after the first compile rejected M5Unified 0.2.19 for
this proof of concept. On every ESP32-S3, `M5Unified::begin()` drives GPIO46
high as an output before board detection. The original Cardputer schematic
connects GPIO46 to the SPM1423 microphone DATA output, and Espressif classifies
GPIO46 as a strapping pin. Disabling the microphone in M5Unified does not undo
that early output configuration. Possible line contention is unnecessary and
outside the accepted hardware boundary.

M5GFX automatic board detection was also rejected for startup. It probes
multiple board configurations and may persist an `AUTODETECT` result in NVS.
Neither behavior is needed when the exact original-board profile is a physical
precondition.

## Decision

Use Arduino CLI 1.5.1 as an unmodified build tool with an isolated build cache.
Use an Arduino sketch build profile that pins:

- Arduino-ESP32 3.3.10;
- M5GFX 0.2.26;
- the board-specific `m5stack_cardputer` target;
- 8 MB flash, QIO boot at 80 MHz, no PSRAM and hardware USB CDC;
- the 8 MB default partition layout;
- 115200 baud upload and full-flash erase disabled.

The build also requires `TOMATO_TARGET_CARDPUTER_ORIGINAL=1` and the
board-package macro `ARDUINO_M5STACK_CARDPUTER`. A missing marker is a build
error.

The application independently defines a fixed ST7789 display configuration
using LovyanGFX primitives from the pinned M5GFX package. It drives only the
original schematic's LCD pins 33 through 38. GPIO0 is an input using the
board's external pull-up. GPIO46 is explicitly held as an input. Backlight PWM
remains zero through display reset and initialization, then changes to a
bounded brightness of 64/255.

There is deliberately no runtime variant autodetection in this image. The
original and Adv share these display and G0 signals, while distinguishing them
would require probing additional keyboard/I2C pins. Physical identification of
the original 2023 ESP32-S3FN8 Cardputer is therefore a mandatory preflight
condition. No keyboard, audio or other variant-sensitive capability is
published or initialized.

Wi-Fi, BLE, microphone, speaker, keyboard, IMU, RTC, SD, infrared, Grove and
external displays are outside this proof of concept.

PlatformIO Core and platform-espressif32 6.7.0 are not selected. The separate
M5Cardputer library is retained as a rejected, reference-only catalog entry. No
source is copied from it. The official M5Cardputer UserDemo V0.9 is registered
as an exact-commit, reference-only source. Its fixed display configuration
corroborates the official schematic; its scripts, binaries and dependencies
were not executed or integrated.

## Threat and isolation plan

The local proof of concept:

- compiles in temporary, isolated data, download, user and build directories;
- downloads only pinned packages from approved Arduino, Espressif and M5Stack
  sources;
- verifies the Arduino CLI archive checksum before execution;
- does not upload firmware, access a serial port or require elevated
  privileges;
- embeds no credentials and initializes no network interface;
- includes a negative build that must reject an unspecified board target.

The compile result is not evidence of behavior on physical hardware. Hardware
acceptance requires physical model verification and separate tests of display
orientation, G0 priority, reboot behavior and power consumption.

## Licensing

Arduino CLI is GPL-3.0-only and remains a build tool; it is not distributed in
the firmware image. Arduino-ESP32 is LGPL-2.1-or-later and M5GFX is MIT.
M5Unified remains cataloged but rejected and is not linked into the firmware.
Versions, commits, checksums and review state are recorded in the upstream
software catalog.

Before distributing a firmware release, the project must produce the firmware
SBOM, preserve applicable notices and confirm source or relinking obligations
for LGPL components.

## Consequences

- Firmware builds are version-pinned and select the original Cardputer at
  compile time; the physical model check remains mandatory.
- Upload configuration is fail-safe against accidental whole-flash erase and
  uses the board-specific target without adding another upstream package.
- The initial binary has no AI, audio, keyboard, radio or network behavior.
- Startup performs no generic hardware probing and does not persist a board
  detection cache.
- A visible `ASSISTANT` indicator cannot silently transition to another
  profile.
- Pressing G0 is sampled before ordinary UI work and records a bounded local
  cancellation request.
- Firmware signing, secure boot, flash encryption, provisioning and credential
  storage remain future decisions.

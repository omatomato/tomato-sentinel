# ADR-0005: Original Cardputer firmware toolchain

- Status: Accepted
- Date: 2026-07-25

## Context

The first physical target is the original M5Stack Cardputer, not Cardputer
Adv. The repository needs a reproducible firmware build before microphone,
keyboard or transport work begins. The first image must prove only a narrow
boundary: explicit board selection, fail-closed board detection, a permanently
visible operating profile and physical cancellation through G0.

Manufacturer documentation presents Arduino IDE, ESP-IDF and PlatformIO as
supported approaches. Its PlatformIO example selects Espressif platform 6.7.0,
which pins Arduino-ESP32 2.0.16. That framework version falls inside several
published vulnerability ranges fixed in 3.3.8 or later.

The M5Cardputer package was also evaluated. Release 1.2.0 has no
repository-level license, declares library version 1.1.1, has no test suite and
pulls IRremote and LibSSH-ESP32 even though the initial firmware needs neither.

## Decision

Use Arduino CLI 1.5.1 as an unmodified build tool with an isolated build cache.
Use an Arduino sketch build profile that pins:

- Arduino-ESP32 3.3.10;
- M5Unified 0.2.19;
- M5GFX 0.2.26;
- the generic ESP32-S3 target with 8 MB flash, no PSRAM and hardware USB CDC.

The build also requires
`TOMATO_TARGET_CARDPUTER_ORIGINAL=1`. A missing target macro is a build error.
Runtime initialization accepts only `board_M5Cardputer`; Cardputer Adv and
unknown boards fail closed without publishing capabilities.

Only display, board detection and the G0 button are enabled. Wi-Fi, BLE,
microphone, speaker, IMU, RTC, external displays and external speakers are
outside this proof of concept.

PlatformIO Core and platform-espressif32 6.7.0 are not selected. M5Cardputer is
retained as a rejected, reference-only catalog entry. No source is copied from
it.

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
acceptance requires a separate test of board detection, display orientation,
G0 priority, reboot behavior and power consumption.

## Licensing

Arduino CLI is GPL-3.0-only and remains a build tool; it is not distributed in
the firmware image. Arduino-ESP32 is LGPL-2.1-or-later. M5Unified and M5GFX are
MIT. Versions, commits, checksums and review state are recorded in the upstream
software catalog.

Before distributing a firmware release, the project must produce the firmware
SBOM, preserve applicable notices and confirm source or relinking obligations
for LGPL components.

## Consequences

- Firmware builds are version-pinned and distinguish the original Cardputer
  from Adv at compile time and runtime.
- The initial binary has no AI, audio, keyboard, radio or network behavior.
- A visible `ASSISTANT` indicator cannot silently transition to another
  profile.
- Pressing G0 is sampled before ordinary UI work and records a bounded local
  cancellation request.
- Firmware signing, secure boot, flash encryption, provisioning and credential
  storage remain future decisions.

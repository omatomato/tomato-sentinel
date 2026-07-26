# Cardputer firmware target

The original M5Stack Cardputer is the primary hardware target for the Tomato
Sentinel MVP and the first device that must pass physical validation.

`board-profile:cardputer-original-v1` is therefore the default development and
test profile. Cardputer-Adv remains an explicit compatibility profile so that
its different audio, keyboard and IMU hardware cannot be mistaken for the
original board. Adv compatibility is not an MVP hardware acceptance target.

The embedded proof of concept is in `app/TomatoSentinel`. It uses the
board-specific `m5stack_cardputer` target from the pinned Arduino-ESP32
platform, initializes only the original board's display, G0 button and fixed
74HC138 keyboard matrix, keeps `PROFILE: ASSISTANT` visible and uses explicit
profiles from the original 2023 schematic. It does not link M5Unified,
M5Cardputer or run generic board autodetection.

Keyboard input is limited to one unshifted key at a time and a 64-byte
RAM-only draft. Multi-key states and modifiers are denied or ignored, Enter
erases the draft without executing or sending it, and G0 has priority and
erases it immediately. No keyboard content is written to logs. Audio, radio,
storage, infrared, Grove and external modules remain uninitialized.

Builds use the exact dependency versions and board options in `sketch.yaml`.
The profile explicitly disables full-flash erase and selects a conservative
115200 baud upload rate. Build only through the safe entry point, which
requires both the original-board compile guard and the link-time NVS guard:

```sh
firmware/cardputer/build-safe.sh <temporary-build-directory>
```

Set `TOMATO_ARDUINO_CLI` only when the pinned Arduino CLI executable is not on
`PATH`. Omitting the original-board marker must fail compilation. Omitting the
link-time NVS guard produces an artifact that is not eligible for hardware
validation. The script contains no upload command. Compilation is not evidence
of behavior on physical hardware.

Do not connect or flash physical hardware from this README alone. Follow
`docs/hardware/original-cardputer-flashing-safety.md`; the first connection is
read-only and an upload requires a separate, explicit confirmation.

The keyboard candidate has not yet been written to hardware. Its design and
remaining physical checks are in
`docs/hardware/original-cardputer-keyboard-poc.md`.

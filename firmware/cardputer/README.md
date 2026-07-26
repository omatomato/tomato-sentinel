# Cardputer firmware target

The original M5Stack Cardputer is the primary hardware target for the Tomato
Sentinel MVP and the first device that must pass physical validation.

`board-profile:cardputer-original-v1` is therefore the default development and
test profile. Cardputer-Adv remains an explicit compatibility profile so that
its different audio, keyboard and IMU hardware cannot be mistaken for the
original board. Adv compatibility is not an MVP hardware acceptance target.

The first embedded proof of concept is in `app/TomatoSentinel`. It initializes
only the original board's display and G0 button, keeps `PROFILE: ASSISTANT`
visible and refuses to start if M5Unified detects another board.

Builds use the exact dependency versions in `sketch.yaml`. The original-board
macro is intentionally separate from the generic ESP32-S3 FQBN:

```sh
arduino-cli \
  --config-file firmware/cardputer/arduino-cli.yaml \
  compile \
  --profile original \
  --build-property \
  build.extra_flags=-DTOMATO_TARGET_CARDPUTER_ORIGINAL=1 \
  firmware/cardputer/app/TomatoSentinel
```

Omitting `build.extra_flags` must fail compilation. Compilation does not upload
the image and is not evidence of behavior on physical hardware.

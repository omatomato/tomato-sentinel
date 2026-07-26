# Cardputer community project source review

- Review date: 2026-07-26 (America/Sao_Paulo)
- Target: original 2023 M5Stack Cardputer with Stamp-S3 / ESP32-S3FN8
- Method: exact detached Git commits, source inspection only
- Result: all three projects rejected for integration or execution

No upstream application code was copied or executed. The visual changes in
Tomato Sentinel are an independent implementation using the already approved
fixed display driver.

## Decision summary

| Project | Exact source | Useful design observation | Reason it is not integrated |
| --- | --- | --- | --- |
| Bruce 1.16 | `59e83bfbd8a63a6b67ea23498e15c710a1ed9657` | board folders, visible state, bounded UI helpers and explicit bus ownership | its Cardputer target combines original and ADV, drives GPIO5, scans I2C 1–126, initializes broad peripherals and includes prohibited offensive functions |
| Evil-M5Project | `78f0289a8dbdd849242a35cd763410c360cb16e5` | persistent status areas and compact menu presentation | no license file was present; one large sketch repeatedly calls broad M5 initialization and includes credential collection, deauthentication, arbitrary HID and other R3 behavior |
| M5Launcher 2.7.2 | `01cf31d9fe1ff8c1ac774b344efb5b05d21016de` | validates flash ranges, image layout and recovery errors before writes | its Cardputer target also probes ADV hardware, drives GPIO5 and its core purpose includes flash erasure, partition writes and boot-partition changes |

## Hardware findings

Bruce and M5Launcher use one `m5stack-cardputer` environment for both the
original keyboard matrix and the ADV TCA8418 controller. At startup they set
GPIO5 as output-high, start I2C on GPIO8/9 and scan every normal I2C address
before falling back to the original keyboard. Bruce additionally configures
the original microphone data on GPIO46 while retaining broad M5Unified-based
initialization and definitions for several radios and buses.

That approach supports many devices and accessories, but it is the opposite of
the narrow first-boot safety boundary required here. Tomato Sentinel selects
the original board at compile time, does not probe for ADV, and initializes
only:

- ST7789 display MOSI 35, SCLK 36, DC 34, CS 37 and reset 33;
- backlight 38, dark during panel initialization and then limited to 64/255;
- G0 as an input for physical cancellation;
- microphone data GPIO46 explicitly as input.

Evil-M5Project calls `M5.begin()` and later `M5Cardputer.begin()` in the same
startup path, immediately scans Wi-Fi and raises transmit power. These are
unnecessary capabilities for the local R0 proof and widen both electrical and
security behavior.

M5Launcher contains valuable defensive checks around alignment, partition
ranges and boot images. It also contains `esp_flash_erase_region`,
`esp_partition_write` and `esp_ota_set_boot_partition` operations. It will not
be used for the first Tomato Sentinel write or recovery procedure. The
manufacturer's factory restore path and the private pre-write backup remain
the documented recovery mechanisms.

## Safe ideas retained independently

The review influenced presentation and process, not implementation source:

- a clear, persistent operating-profile badge;
- one large current-state panel instead of a dense feature menu;
- explicit indicators that radio and audio are off;
- a high-contrast, persistent G0 cancellation affordance;
- validation of exact flash ranges and hashes before any future write;
- visible failure states rather than optimistic success claims.

No menus for offensive actions, generic scripting, arbitrary HID, credential
capture, radio transmission, network attacks or firmware switching are
eligible for Tomato Sentinel. R3 actions cannot be registered, proposed or
executed under the repository authorization model.

## License and provenance result

- Bruce 1.16 declares `AGPL-3.0-only`. It is retained only as an immutable
  source-review reference; no code is copied.
- Evil-M5Project had no root license file or license declaration identifiable
  in the reviewed commit. Its code is therefore not reusable, independently of
  the R3 rejection.
- M5Launcher 2.7.2 declares `MIT`, but license compatibility does not make its
  state-changing flash functionality suitable for this proof.

Exact provenance and rejection notes are recorded in
`config/upstream/software-catalog.yaml`.

## Primary sources

- [M5Stack original Cardputer documentation][m5-cardputer]
- [Bruce 1.16 exact source][bruce]
- [Evil-M5Project exact source][evil]
- [M5Launcher 2.7.2 exact source][launcher]

[m5-cardputer]: https://docs.m5stack.com/en/core/Cardputer
[bruce]: https://github.com/BruceDevices/firmware/tree/59e83bfbd8a63a6b67ea23498e15c710a1ed9657
[evil]: https://github.com/7h30th3r0n3/Evil-M5Project/tree/78f0289a8dbdd849242a35cd763410c360cb16e5
[launcher]: https://github.com/bmorcelli/Launcher/tree/01cf31d9fe1ff8c1ac774b344efb5b05d21016de

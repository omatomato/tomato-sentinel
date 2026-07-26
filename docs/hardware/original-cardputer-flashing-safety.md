# Original Cardputer flashing safety

This procedure applies only to an original M5Stack Cardputer. Cardputer-Adv is
not an interchangeable target.

Firmware upload is an active, state-changing local operation (`R2`). It
requires the exact physical device, an operator present at the computer and a
fresh explicit confirmation immediately before the write. Compilation and
read-only inspection do not authorize an upload.

## Permanent-damage boundary

A normal ESP32-S3 serial upload writes SPI flash and does not program eFuses or
change supply voltages. It can still replace the factory firmware or leave the
device unable to boot until recovery if the image, offsets, connection or power
is wrong. No procedure can promise zero risk.

Physical damage is primarily controlled by using an intact USB-C data cable,
disconnecting external modules and avoiding shorts or non-standard power.
Software risk is controlled by the staged checks below.

The original Cardputer's side switch physically connects the 5 V input/output
path. The current firmware cannot be treated as a software disconnect for that
rail. Nothing may be attached to Grove, the Stamp headers or other external
power pins during first validation.

## Prohibited commands and options

For the first hardware validation:

- never run `erase-flash`, `erase-all`, `erase-region` or an upload with
  `EraseFlash=all`;
- never use `--force`;
- never run eFuse, Secure Boot, flash-encryption or write-protection commands;
- never upload a padded, merged 8 MB image;
- never guess a serial port, chip, flash size, offsets or security state;
- never continue after a disconnect, brownout, verification failure or
  unexpected device identity.

## Stage 0: prepare without the device

1. Build from the pinned `original` profile.
2. Require the independent
   `TOMATO_TARGET_CARDPUTER_ORIGINAL=1` compile-time guard.
3. Inspect the generated bootloader and application image offline.
4. Confirm ESP32-S3, 8 MB, DIO image header, 80 MHz and valid image hashes.
5. Inspect every image and offset in the generated upload recipe; do not
   execute that multi-image recipe against an existing device.
6. Confirm `UploadSpeed=115200` and `EraseFlash=none`.
7. Confirm the application does not link M5Unified or automatic board
   detection and that GPIO46 is configured only as input.

The generated recipe is evidence to inspect, not authorization to use it.
The official UserDemo V0.9 partition layout differs from the Arduino
`default_8MB` layout. No upload recipe is approved until the connected
device's actual partition table is read, decoded and compared. See
`docs/hardware/cardputer-fail-safe-mode.md`.

## Stage 1: first connection is read-only

Remove the microSD card and disconnect all Grove or external modules as a
precaution. Set the side power switch to `OFF`. Hold G0, connect a known-good
USB-C data cable directly to the computer, then release G0.

Before any write:

1. identify the newly appeared serial device without guessing;
2. require the chip to identify as ESP32-S3;
3. read the flash ID and require the detected size to be exactly 8 MB;
4. read the security information and stop on Secure Boot, flash encryption,
   Secure Download Mode or any unexpected restriction;
5. read and hash a complete 8 MB flash backup.
6. separately read and decode the partition table at `0x8000`;
7. stop if its entries, MD5, application subtype or bounds are unexpected.

The backup may contain Wi-Fi credentials, identifiers or other private factory
data. Store it outside the repository with restrictive permissions and never
publish or commit it.

### Observed preflight

Read-only preflight completed on 2026-07-26 against the connected original
Cardputer:

- ESP32-S3 QFN56 revision 0.2;
- embedded GD flash, JEDEC `c8:4017`, 8 MB, quad data lines at 3.3 V;
- USB Serial/JTAG;
- Secure Boot and flash encryption disabled;
- complete 8 MB backup stored outside the repository with mode `600`;
- independently reread partition-table sector matched the backup byte for
  byte;
- valid table with `app0` at `0x10000`, size 3 MB, and no second application
  slot.

The private manifest holds the device-specific backup path and hash. MAC and
other device identifiers must not be copied into repository documentation.

## Stage 2: exact write plan

Before upload, show the operator:

- the resolved serial port and detected chip/flash identity;
- the security-state result;
- the backup path, size and SHA-256;
- hashes for every generated image;
- the exact offsets and byte ranges that will change;
- confirmation that full-flash erase, `--force` and eFuse operations are
  absent.

Only a new explicit approval for that exact plan authorizes the upload.

There is currently no approved write command. The Arduino-ESP32 recipe is not
acceptable because it would replace the bootloader, partition table, OTA
metadata and application.

For this observed device, a candidate plan may target only the application
image at `0x10000`. Its padded erase/write range must remain entirely inside
the observed 3 MB `app0` partition. It must preserve every other range,
especially the bootloader, partition table, OTA data, NVS and SPIFFS. Because
there is no inactive application slot, the plan must present and validate the
manual ROM recovery command before the write is authorized.

The exact plan must use 115200 baud, omit full-flash erase, `--force`, eFuse
operations and generated non-application images, and verify the application
range after writing. Do not use M5Burner for the Tomato Sentinel custom
sketch.

## Stage 3: verification and recovery

Require successful post-write hash verification before disconnecting. Then
boot normally and validate the display, bounded backlight, persistent profile
indicator and G0 cancellation. Stop immediately on unexpected heat, odor,
display instability, repeated resets or abnormal current draw.

M5Burner is retained only as the manufacturer-documented path for restoring
official factory firmware. The private full-flash backup is the path for
restoring the exact pre-test state. Recovery is attempted only after recording
the failure and reviewing the observed boot/download-mode behavior.

### Observed first application write

On 2026-07-26, after fresh operator confirmation, esptool wrote only the
selected 346,912-byte application at `0x10000`. The reported sector erase
range was `0x10000` through `0x64fff`, entirely inside the observed 3 MB
`app0` partition. Bootloader, partition table, OTA data, NVS, SPIFFS and
coredump ranges were not included in the command.

The write completed its built-in hash verification, and a separate
`verify-flash` operation matched the selected application digest. The device
remained in ROM download mode until the operator manually pressed Reset.

The operator reported:

- the expected ready screen and visible `ASSISTANT` profile;
- no abnormal heat, odor, flicker or repeated resets;
- G0 changed the UI to the expected cancel-requested safe state;
- a subsequent manual Reset returned to the normal ready state.

USB enumeration remained stable after the test. Battery-powered operation,
the side switch in `ON`, deliberate watchdog/panic recovery and capabilities
excluded from this proof of concept were not tested.

### Subsequent keyboard/UI candidate

The `0.2.1-poc` keyboard and UI candidate requires a separate R2 approval; the
approval for the first application write does not carry forward. A fresh
read-only ROM preflight on 2026-07-26 reconfirmed the same original ESP32-S3,
8 MB flash, security state and byte-identical partition table.

The 348,912-byte candidate would occupy `0x10000` through `0x652ef` and cause
esptool to erase sectors `0x10000` through `0x65fff`, still entirely inside
`app0`. A new private mode-`600` recovery slice covers that complete erase
range and preserves the exact application state present immediately before
the proposed write.

After explicit confirmation of that exact plan, esptool 5.3.0 erased only
`0x10000` through `0x65fff` and wrote the 348,912-byte candidate at `0x10000`.
Its built-in hash verification passed, followed by an independent
`verify-flash` digest match over all candidate bytes. The commands used the
ESP32-S3 ROM without a RAM stub, preserved flash settings, performed no reset
and left the device in bootloader mode for a manual operator-controlled boot.
After manual Reset, the operator reported that the redesigned `0.2.1-poc`
interface booted and functioned normally. This is initial display evidence,
not yet full keyboard, cancellation, reset-recovery, thermal or soak-test
acceptance.

### One-shot Shift update

Before the `0.2.2-poc` update, a fresh ROM preflight reconfirmed hardware,
security and the byte-identical partition table. `verify-flash` matched the
physically accepted `0.2.1-poc`, and the complete current erase range was
stored privately for exact rollback.

After a separate exact R2 confirmation, esptool erased only `0x10000` through
`0x65fff` and wrote the 349,472-byte `0.2.2-poc` image at `0x10000`. Built-in
hash verification and a separate full `verify-flash` digest comparison both
passed. The device was left in ROM mode without automatic reset; physical
one-shot Shift behavior was then accepted through staged uppercase, symbol,
manual-disarm, Enter-clear, G0-clear/lock and Reset-recovery checks. No
simultaneous-key chord was required.

Subsequent staged input checks displayed `1qaz`, applied Backspace, discarded
the draft on Enter and suppressed repetition while `m` was held. G0 then
cleared the active one-character draft, displayed the expected cancelled safe
state and blocked a subsequent `a` input. Reset recovery, the 64-byte bound and
ambiguous multi-key denial remain separate checks.

A subsequent manual Reset returned to `DEVICE READY / LOCAL CONSOLE` without
entering fail-safe mode. A single `x` input then appeared with count `1/64`,
confirming keyboard re-enablement. The initial physical keyboard/UI milestone
is accepted for the observed sequences; the 64-byte limit and ambiguous
multi-key denial were not deliberately exercised on hardware.

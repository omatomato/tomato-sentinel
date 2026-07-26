# Original Cardputer fail-safe mode

The operator-facing nickname “anti-merda mode” means a bounded fail-safe and
anti-brick design. It does not mean the firmware can promise zero risk or
repair arbitrary damage automatically.

## Threat boundary

The first physical validation must survive or remain recoverable from:

- an application crash or watchdog reset during early startup;
- a corrupted or invalid candidate application;
- an unstable power supply detected as brownout;
- a display-driver initialization failure;
- a partition layout that differs from the expected layout;
- an interrupted write.

It does not protect against physical shorts, incorrect supply voltage, damaged
flash hardware, irreversible eFuse changes or disabled ROM download mode.
Those actions remain prohibited.

## Layer 1: immutable ROM recovery

The ESP32-S3 enters its serial ROM bootloader when GPIO0 is low during reset,
provided the security state has not disabled download mode. On the original
Cardputer the manufacturer procedure is:

1. side power switch `OFF`;
2. hold G0;
3. connect USB power/data;
4. release G0 after power is present.

This recovery path runs before the second-stage bootloader and application.
Tomato Sentinel never writes eFuses, enables Secure Boot, enables flash
encryption, enables anti-rollback or disables ROM download mode.

## Layer 2: flash-free crash-loop guard

The application stores a small checksummed state in RTC no-init memory. It
marks startup as in progress before display initialization and clears the mark
only after five seconds of healthy loop execution.

Two consecutive resets while startup is unfinished latch fail-safe mode on the
following boot. Power-on, external reset and deep-sleep reset start a clean
sequence. Fail-safe mode:

- shows a high-contrast warning;
- keeps the `ASSISTANT` profile visible;
- keeps radio and audio capabilities absent;
- performs no automatic repair or flash write;
- remains latched for that boot even after health is established.

RTC memory is not durable storage and may be lost on power removal. It is a
crash-loop signal, not a substitute for ROM recovery or a full flash backup.

## Layer 3: pre-setup write guards

Exact Arduino-ESP32 3.3.10 source review found two default behaviors before
the sketch's `setup()`:

- a pending OTA image is accepted immediately by the default weak
  `verifyOta()` hook;
- `nvs_flash_init()` may erase the NVS partition when it reports no free pages
  or a newer incompatible version.

Tomato Sentinel overrides `verifyRollbackLater()` to defer all OTA acceptance.
The safe build also link-wraps `nvs_flash_init()` with a function that returns
`ESP_ERR_NOT_SUPPORTED`. The framework therefore logs an initialization error
but cannot enter its automatic NVS-format branch.

As a defense in depth against future framework changes, the same build replaces
the public partition-write, partition-erase, raw-flash-write and
raw-flash-erase entry points with fail-closed stubs. These guards affect only
the running candidate application. They do not interfere with read-only ROM
inspection or with a separately approved esptool recovery operation.

The safe build also preserves the platform's own USB flags instead of
overwriting `build.extra_flags`. It requires hardware CDC/JTAG mode, disables
Arduino's global UART instances with `NO_GLOBAL_SERIAL`, and logs only through
`HWCDCSerial`. The explicit `Serial=HWCDCSerial` compiler mapping keeps
framework diagnostics on that same native USB interface without reinstating
UART globals. This prevents the framework from assigning UART0 TX/RX to the
ESP32-S3 defaults GPIO43/44, which overlap original Cardputer audio and IR
connections.

This protection is part of the exact build command, not merely application
source. `firmware/cardputer/build-safe.sh` contains compilation only and
requires the linker wrappers. A separate
`TOMATO_RUNTIME_WRITE_GUARDS=1` compile marker makes ordinary builds fail when
the safe entry point is bypassed. It has no upload command.

## Layer 4: hardware protections already in the pinned build

Offline inspection of the generated Arduino-ESP32 3.3.10 configuration
confirmed:

- 9-second second-stage boot watchdog;
- 300 ms interrupt watchdog;
- 5-second task watchdog with panic/reset behavior;
- task watchdog monitoring of CPU0 idle;
- brownout detector enabled at the framework's ESP32-S3 level 7 setting;
- Secure Boot and flash encryption disabled.

The application explicitly subscribes the Arduino loop task to the task
watchdog. Failure to verify that subscription latches fail-safe mode.

## Layer 5: partition-layout refusal

Rollback is not assumed merely because the framework was compiled with OTA
rollback support. Espressif documents that rollback applies to OTA partitions
and requires a previously valid application.

The reviewed official M5Cardputer UserDemo V0.9 uses:

```text
nvs      0x009000 0x005000
phy_init 0x00f000 0x001000
factory  0x010000 0x400000
storage  automatic 0x100000
```

The current Arduino `default_8MB` candidate instead generates `otadata` and
two OTA application slots. Replacing a device partition table with that
generated table would destroy the assumption that its existing firmware
remains a bootable fallback.

Read-only preflight of the connected original Cardputer on 2026-07-26 found a
third layout:

```text
nvs      0x009000 0x005000
otadata  0x00e000 0x002000
app0     0x010000 0x300000
spiffs   0x310000 0x0e0000
coredump 0x3f0000 0x010000
```

The complete 8 MB flash was read through the ESP32-S3 ROM without a RAM stub,
stored outside the repository with restrictive permissions and hashed. A
separate read of the partition-table sector matched the corresponding backup
bytes, and the table's MD5 and bounds validated. Security inspection reported
Secure Boot and flash encryption disabled. Device identifiers and the private
backup hash remain outside repository documentation.

The observed table has one 3 MB OTA application partition and no inactive
application slot. The candidate application fits inside `app0`, but there is
no automatic fallback image. Therefore:

- never write the generated bootloader, partition table or `boot_app0`;
- never write NVS, OTA data, SPIFFS, coredump or the unpartitioned upper 4 MB;
- do not claim OTA rollback as a recovery control;
- treat manual ROM restoration from the private backup as the recovery path;
- require a fresh exact-range approval before any application-only write.

There is still no approved write command. The application-only plan, recovery
command and verification command must be reviewed together before asking the
operator for R2 confirmation. A layout mismatch remains a hard refusal, not
permission to “fix” the device.

## Tests

Compile-time assertions exercise:

- invalid RTC state recovery;
- first failed startup remaining below the threshold;
- second consecutive failed startup entering fail-safe mode;
- healthy-state clearing.

Static tests reject NVS, OTA, partition, raw-flash and eFuse mutation APIs in
the crash-loop guard. They also require the pre-setup overrides and the NVS
link wrapper, and reject upload or write-flash commands in the safe build
script. Positive and wrong-target firmware builds remain mandatory.

Read-only identity, security, flash-ID, full-backup and partition-layout
inspection have been completed on the original Cardputer. On 2026-07-26, the
operator explicitly approved an application-only R2 write. The selected image
was written at `0x10000`, remained inside the observed `app0` partition and
passed both esptool's post-write hash check and a separate `verify-flash`
digest comparison.

The operator then reported the expected ready screen without abnormal heat,
odor, flicker or reset behavior. Pressing G0 displayed the expected bounded
cancel state, and a manual Reset returned to the ready state rather than
fail-safe mode. This is evidence for that observed sequence only; it is not an
electrical measurement or proof of every crash path.

## Official references

- [M5Stack Cardputer download mode][cardputer]
- [M5Stack factory restore procedure][factory-restore]
- [Espressif ESP32-S3 boot-mode selection][boot-mode]
- [Espressif bootloader watchdog and factory-reset behavior][bootloader]
- [Espressif OTA rollback limits][ota]
- [Espressif task watchdog behavior][watchdogs]
- [Espressif brownout behavior][fatal-errors]

[cardputer]: https://docs.m5stack.com/en/core/Cardputer
[factory-restore]: https://docs.m5stack.com/en/guide/restore_factory/cardputer
[boot-mode]: https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html
[bootloader]: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/bootloader.html
[ota]: https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32s3/api-reference/system/ota.html
[watchdogs]: https://docs.espressif.com/projects/esp-idf/en/v5.3.3/esp32s3/api-reference/system/wdts.html
[fatal-errors]: https://docs.espressif.com/projects/esp-idf/en/v4.4/esp32s3/api-guides/fatal-errors.html

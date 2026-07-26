# Original Cardputer local keyboard proof of concept

- Design date: 2026-07-26 (America/Sao_Paulo)
- Target: original 2023 M5Stack Cardputer / Stamp-S3 / ESP32-S3FN8
- Firmware version: `0.2.2-poc`
- Risk: local R0 input handling; a later firmware upload remains R2
- Hardware status: uploaded, independently verified and physically accepted for
  the observed sequences documented below

## Boundary

This increment adds a bounded local text draft. It does not add a registered
tool, command execution, transport, Wi-Fi, BLE, audio, storage, credentials or
provider access. Enter explicitly discards the draft and performs no action.
G0 is sampled first, erases the draft and permanently stops keyboard handling
for the current boot.

The draft holds at most 64 bytes in RAM. Its contents may appear on the local
screen but never in USB logs. Enter, G0 and reset remove the only application
copy; the explicit clear uses volatile writes so it is not optimized away.
This is transient operator input and must not be treated as authentication,
authorization or an executable command.

No role, resource grant, operation scope or confirmation is applicable to
local R0 text entry because it cannot cause a side effect. Compiling and
inspecting the image is also read-only. Writing the image to physical flash is
a separate R2 operation and requires a fresh exact-plan confirmation.

## Electrical design

The official original Cardputer schematic connects:

- GPIO8, GPIO9 and GPIO11 to the A0, A1 and A2 address inputs of the onboard
  74HC138;
- GPIO13, GPIO15, GPIO3, GPIO4, GPIO5, GPIO6 and GPIO7 to the seven keyboard
  sense lines through 22 ohm series resistors.

Only the three address pins become outputs. A low output latch is loaded before
their direction changes, then the selector is advanced through exactly eight
values. The seven sense pins are always `INPUT_PULLUP`. Each selector change
gets a fixed 5 microsecond settling interval, and the selector returns to zero
after every scan.

The implementation does not probe for Cardputer-Adv, does not start I2C and
does not include M5Cardputer. M5Cardputer 1.2.0 at the exact commit already
registered in the upstream catalog was inspected only to corroborate the
manufacturer schematic, pin order, active-low sense and matrix geometry. The
driver and bounded state machine are independent implementations.

## `0.2.1-poc` baseline denial controls

- A state with zero keys produces no event.
- A state with more than one key produces `MULTI-KEY DENIED`; this avoids
  ambiguous chords and matrix ghosting in the initial slice.
- Shift, Fn, Ctrl, Opt, Alt and Tab are ignored.
- Only the unshifted printable layer, Backspace and Enter are accepted.
- A held key produces one event only after 30 milliseconds of stable input.
- A 65th byte is denied without changing the existing draft.
- Safe mode does not initialize or poll the keyboard.
- After G0 cancellation, the keyboard is no longer polled during that boot.
- USB logs contain only discarded byte counts, never draft content.

## Interface design

Version `0.2.1-poc` replaces the diagnostic-looking screens with one compact
visual system implemented entirely with fixed M5GFX drawing primitives:

- a graphite background and raised content card;
- a small tomato mark and persistent `ASSISTANT` profile pill;
- green reserved for healthy/local state, amber for fail-safe state and red
  for denial or cancellation;
- separate ready, draft, fail-safe and cancelled compositions;
- a bounded draft field, `0/64` counter and persistent action footer.

The interface uses no bitmap, sprite, downloaded font, dynamic allocation or
new dependency. All labels remain ASCII for compatibility with the built-in
font. Layout constants target only the original display's 240x135 landscape
geometry. Presentation code lives in `TomatoSentinelUi.h`; keyboard decoding,
draft state and safety decisions remain separate.

## Test plan before any upload

1. Compile through `firmware/cardputer/build-safe.sh` only.
2. Run repository formatting, lint, type checks and tests.
3. Confirm the application image remains inside the observed 3 MB `app0`.
4. Inspect linked symbols again for flash writes, M5Unified/M5Cardputer,
   network, audio and UART initialization.
5. Review the exact application hash, write/erase range and recovery slice.
6. Request a new R2 confirmation for that exact candidate.

Physical acceptance, only after an authorized write:

1. Reset to the ready screen and observe for heat, odor, flicker or reset loops
   before touching the keyboard.
2. Press representative keys from all four physical rows and both even/odd
   columns; confirm the displayed characters match.
3. Verify one held key does not repeat.
4. Verify two simultaneous keys display `MULTI-KEY DENIED`.
5. Fill 64 bytes and verify the next byte is denied.
6. Verify Backspace changes only the local draft.
7. Press Enter and verify the draft is erased, no action runs and logs reveal
   only its prior byte count.
8. Type a draft, press G0 and verify immediate erase, persistent cancel UI and
   no further keyboard response until reset.
9. Reset and confirm return to ready state without fail-safe mode.

Any wrong key mapping, continuous key detection, abnormal display behavior,
USB instability, heat, odor or repeated reset is a stop condition. Simulator
and compile results are not evidence of physical keyboard behavior.

## Offline verification result

The safe compile completed without an upload command:

```text
Sketch uses 348763 bytes (10%) of program storage space.
Global variables use 22516 bytes (6%) of dynamic memory.
```

The flashable application is 348,912 bytes:

```text
SHA-256 41e7c38dfe8236ad71512c2e0c278b7f9aa03c9c5a13507067203c3722d1e187
```

Offline image inspection reports ESP32-S3, 8 MB, DIO at 80 MHz, a valid
checksum and a valid embedded validation hash. At the observed device's
`0x10000` application offset, its byte range would be
`0x10000` through `0x652ef`; the corresponding sector erase range would be
`0x10000` through `0x65fff`. Both remain within the observed 3 MB `app0`.
These values describe a candidate only and are not an approved write plan.

Linked-symbol inspection found the fail-closed NVS, partition and raw-flash
write/erase wrappers and the OTA deferral override. It found no linked
M5Cardputer, M5Unified, Cardputer-Adv detection, Wi-Fi, hardware UART or OTA
state-changing symbol in the application. Framework archives can contain
unused code and diagnostic strings; the conclusion is based on the linked ELF
symbols, not a raw string search alone.

Repository checks completed with 145 tests passing, Ruff formatting and lint
passing, and mypy passing. A negative compile without
`TOMATO_TARGET_CARDPUTER_ORIGINAL=1` failed at the mandatory original-board
`#error`.

The exact candidate was copied to the existing private recovery directory with
mode `600`, and the copied SHA-256 matched. Its private absolute path is not
published in repository documentation.

### Physical preflight for `0.2.1-poc`

Immediately before any possible write, a new read-only ROM preflight on
2026-07-26 reconfirmed:

- ESP32-S3 QFN56 revision 0.2 with embedded GD 8 MB flash;
- USB Serial/JTAG and 3.3 V quad flash;
- Secure Boot and flash encryption disabled;
- the 4 KiB partition-table read matched the private prior copy byte for byte;
- `app0` remains at `0x10000` with size 3 MB.

The larger visual candidate still has the same `0x10000` through `0x65fff`
sector erase range calculated offline. Because the first physical candidate's
minimal recovery slice ended at `0x64fff`, the complete current device range
`0x10000` through `0x65fff` was reread before requesting approval. The new
352,256-byte recovery slice was stored privately with mode `600` and its copied
hash matched. No write, erase, reset, stub upload or application boot occurred
during this preflight.

### Authorized application write

After the operator explicitly authorized the exact `0.2.1-poc` candidate and
erase range, esptool 5.3.0 wrote only the 348,912-byte application at
`0x10000`, through the ESP32-S3 ROM at 115200 baud without a RAM stub. Esptool
reported the expected sector erase range `0x10000` through `0x65fff`; no other
image or address was present in the command.

The write's built-in hash verification passed. A separate `verify-flash`
operation then compared all 348,912 bytes at `0x10000` with the selected
candidate and reported a matching digest. Both commands used `no-reset`
before and after, so the device remained in ROM bootloader mode. Physical UI,
keyboard, heat, odor, flicker, reset-loop and cancellation acceptance remain
unverified until the operator manually resets and observes the device.

### Initial physical boot observation

After the manual Reset, the operator reported that `0.2.1-poc` booted and the
redesigned interface was functioning normally. No failure symptom was
reported. This accepts the observed initial boot and display presentation
only; individual keyboard mapping, debounce, limits, Enter discard, G0
cancellation, reset recovery and longer-duration physical behavior remain
separate checks.

### Initial physical keyboard observation

The operator then pressed and fully released `1`, `q`, `a` and `z` in
sequence. The local draft displayed `1qaz` with count `4/64`, covering all
four physical keyboard rows and more than one selector/sense path. Backspace
changed the draft to `1qa` with count `3/64`. Enter cleared the draft and
displayed `DISCARDED / NO ACTION`, as designed.

The operator next held `m` for approximately two seconds. Exactly one `m` was
displayed with count `1/64`; no repeated character appeared while the key was
held. This confirms held-key suppression for that observed input.

With the one-character draft still present, the operator pressed G0. The
device displayed `CANCEL REQUESTED / SAFE STATE`, cleared the draft and showed
`INPUT LOCKED`. Pressing `a` afterward did not change the UI. This confirms
physical-cancel priority, RAM draft clearing and the post-cancel input lock in
that observed sequence.

The operator then pressed Reset once. The device returned to
`DEVICE READY / LOCAL CONSOLE` without entering fail-safe mode, and pressing
`x` produced `x` with count `1/64`. This confirms clean reset recovery and
keyboard re-enablement in that observed sequence.

The 64-byte bound and ambiguous multi-key denial remain covered by static and
compile-time controls but have not been deliberately exercised on physical
hardware.

## Next offline candidate: one-shot Shift

Version `0.2.2-poc` adds one-shot Shift without enabling simultaneous-key
chords. Pressing and releasing Shift alone arms the next printable key; the UI
shows `SHIFT ARMED / NEXT KEY` and highlights the counter in amber. The next
key uses the uppercase/symbol layer and immediately disarms Shift. Pressing
Shift again disarms it without changing the draft.

Enter and G0 both clear the one-shot state. Multi-key input remains denied,
and Fn, Ctrl, Opt, Alt and Tab remain ignored. This preserves the single-key
electrical and ambiguity boundary physically validated by `0.2.1-poc`.

The safe build completed with 146 tests passing:

```text
Sketch uses 349323 bytes (10%) of program storage space.
Global variables use 22516 bytes (6%) of dynamic memory.
```

The flashable application is 349,472 bytes:

```text
SHA-256 fe83be2a111ada6e9baefc6434c3fa85ac7f31a7e167ec65e3dd98dc65621037
```

Its application byte range was calculated as `0x10000` through `0x6551f`; its
sector erase range remained `0x10000` through `0x65fff`. The exact candidate
was preserved privately with mode `600`. Its later authorized write and
physical acceptance are documented below.

### Read-only preflight for `0.2.2-poc`

After the operator returned the device to ROM mode, a fresh read-only preflight
reconfirmed the original ESP32-S3 revision, GD 8 MB flash, 3.3 V quad mode,
disabled Secure Boot and disabled flash encryption. The partition table again
matched the private reference byte for byte.

An independent `verify-flash` confirmed that the application present on the
device still exactly matched the physically accepted `0.2.1-poc` candidate.
The complete current `0x10000` through `0x65fff` range was then read and stored
as a new private mode-`600` rollback slice:

```text
Size: 352256 bytes
SHA-256 d86b425f86ee27b755455d6ff7483dc0e8502ddbeb6fa8fd5d4a971096e5102f
```

No write, erase, reset or RAM stub upload occurred during this preflight.
`0.2.2-poc` still required a separate exact R2 authorization.

### Authorized `0.2.2-poc` write

After exact operator authorization, esptool 5.3.0 erased only `0x10000`
through `0x65fff` and wrote the 349,472-byte `0.2.2-poc` candidate at
`0x10000`. The command contained no other image or address, used the ESP32-S3
ROM without a RAM stub at 115200 baud, preserved flash settings and performed
no reset.

The built-in hash verification passed. A separate `verify-flash` then matched
all 349,472 candidate bytes. Both commands left the device in ROM bootloader
mode; the operator then performed the manual Reset and physical acceptance
described next.

After manual Reset, the operator reported the expected ready screen. Pressing
and releasing Shift alone displayed `SHIFT ARMED / NEXT KEY` with the amber
counter. Pressing `a` then produced uppercase `A` with count `1/64` and
automatically disarmed Shift. This accepts the observed one-shot uppercase
transition.

The operator then entered Shift+`1` and Shift+`/` as sequential one-shot
inputs, producing `!` and `?`. Pressing Shift twice displayed
`SHIFT DISARMED`, and the following `z` remained lowercase. The resulting
draft was `A!?z` with count `4/64`. This accepts the observed symbol layer and
manual disarm behavior. Enter/G0 clearing of armed Shift and reset recovery
remain separate checks.

For the final staged check, the operator armed Shift and pressed Enter. The
`A!?z` draft was discarded, the Shift state cleared, and the following `a`
remained lowercase. Shift was armed again, then G0 cleared the active draft,
displayed the cancelled safe state and locked input. After Reset, a new `a`
again appeared lowercase with count `1/64`.

The `0.2.2-poc` one-shot Shift milestone is physically accepted for all
observed sequences above. The device still has no radio, audio, persistence,
credentials, transport or executable command path.

## Primary sources

- [M5Stack original Cardputer documentation][cardputer]
- [M5Stack original Cardputer schematic][schematic]
- [M5Cardputer 1.2.0 exact keyboard matrix source][matrix]
- [M5Cardputer 1.2.0 exact key map][key-map]

[cardputer]: https://docs.m5stack.com/en/core/Cardputer
[schematic]: https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/481/Sch_M5Cardputer.pdf
[matrix]: https://github.com/m5stack/M5Cardputer/blob/2d4fa6646e4e5b47e0af96214b003aa7b15b8d81/src/utility/Keyboard/KeyboardReader/IOMatrix.cpp
[key-map]: https://github.com/m5stack/M5Cardputer/blob/2d4fa6646e4e5b47e0af96214b003aa7b15b8d81/src/utility/Keyboard/Keyboard.h

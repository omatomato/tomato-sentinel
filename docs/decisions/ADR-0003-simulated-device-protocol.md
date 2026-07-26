# ADR-0003: Define the simulated Cardputer device protocol

- Status: Accepted
- Date: 2026-07-25

## Context

The simulated monitoring MVP now needs a Cardputer-side trust boundary without
claiming that firmware, secure storage or physical hardware has been tested.
The original Cardputer and Cardputer-Adv differ in audio, keyboard and IMU
hardware, so one implicit pin map is unsafe.

Official hardware references reviewed:

- [Cardputer](https://docs.m5stack.com/en/core/Cardputer);
- [Cardputer-Adv](https://docs.m5stack.com/en/core/Cardputer-Adv);
- [Cardputer microphone guidance](https://docs.m5stack.com/en/arduino/m5cardputer/mic).

No upstream library or firmware source is incorporated by this decision.

## Decision

### Board profiles

Maintain explicit declarative profiles for the original Cardputer and
Cardputer-Adv. Profiles declare logical drivers, pins, trusted built-in
capabilities and resource conflicts.

Capability reports are derived from a loaded, validated board profile. An
incoming report is accepted only when it exactly matches the provisioned
device profile.

### Protocol envelope

Protocol version 1 uses bounded canonical JSON envelopes containing:

- message ID and monotonic sequence;
- device ID and timestamp;
- correlation ID and payload type;
- payload;
- authentication algorithm, key ID and tag.

The receiver rejects unknown devices, revoked credentials, invalid tags,
unsupported versions, stale or future timestamps, reused message IDs,
non-increasing sequences, unknown payload types and oversized messages.

The in-memory simulator retains the latest 1,024 message IDs per device and a
monotonic last-sequence value. Production replay persistence across process
restart is not implied.

### Simulation authentication

The simulator uses per-device HMAC-SHA256 keys and constant-time verification.
This proves canonicalization, device separation and replay behavior only.

HMAC is not the production firmware identity decision. Device key storage,
asymmetric identity, secure boot, signed firmware and rollback protection
require a later firmware-security ADR and hardware validation.

HMAC also does not provide payload confidentiality and therefore does not
satisfy the production authenticated-encryption requirement. No network
transport is introduced by this simulator.

### Device profiles

The simulator boots into `assistant`. The active profile is always exposed as a
visible indicator. Entering `lab` requires an unlocked device, operator
identity, active scope and expiry of at most 30 minutes. Reboot and expiry
return the simulator to `assistant`.

A signed device profile claim does not create server authorization. The
existing policy engine still evaluates the command profile, actor, device,
grant or scope and tool requirements.

### Cancellation

A physical cancel input creates a signed, bounded `cancel_request`. After
transport verification, the backend resolves the exact job and invokes its
existing cooperative cancellation path. Cancellation messages cannot choose
arbitrary tools or parameters.

## Consequences

- Protocol and policy behavior can be tested without hardware or network I/O.
- Board differences are explicit before C++ code exists.
- The simulator must never be described as production-grade device identity.
- Push-to-talk audio buffers, real key storage and firmware compilation remain
  future work.

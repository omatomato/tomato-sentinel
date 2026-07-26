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

The original Cardputer is the primary MVP hardware and physical-validation
target. The Adv profile exists for explicit future compatibility and is not an
MVP acceptance target.

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

The in-memory simulator retains the latest 1,024 message IDs per device and key
generation, plus a monotonic last-sequence value for that identity generation.
Production replay persistence across process restart is not implied.

### Simulation authentication

The simulator uses per-device HMAC-SHA256 keys and constant-time verification.
This proves canonicalization, device separation and replay behavior only.

HMAC is not the production firmware identity decision. Device key storage,
asymmetric identity, secure boot, signed firmware and rollback protection
require a later firmware-security ADR and hardware validation.

HMAC also does not provide payload confidentiality and therefore does not
satisfy the production authenticated-encryption requirement. No network
transport is introduced by this simulator.

### Simulated identity lifecycle

The in-memory registry models explicit provisioning, server-side status, key
rotation and revocation. Provisioning is a deliberate registry call for one
known device; discovery input is never accepted by this interface and cannot
create an identity.

Secrets enter only the in-memory registry API. They are absent from public
models, status contracts, return values and reason-coded errors. Status reports
the device ID, current key ID, board profile, firmware version, monotonic
identity revision and `trusted` or `revoked` state, and is always labelled
`execution_mode: simulation`.

Rotation requires the exact current key ID, a distinct well-formed new key ID
and at least 32 bytes of new simulation key material. Retired key IDs cannot be
reused, and secret material cannot be shared between device identities or
generations. Each simulated device is limited to 64 rotations. A retry with the
same transition and same new key material is idempotent; a repeated key ID with
different material is denied. Replay state is keyed by device and current key
ID so a legitimately rotated device can start a new sequence while old-key
messages fail authentication-context checks.

Revocation requires the exact current key ID, is idempotent, increments the
identity revision once and immediately blocks message verification and later
rotation. Unknown devices remain unknown and are not implicitly registered.

These methods are simulator configuration primitives, not remotely callable
tools or operator-facing authorization endpoints. Production provisioning,
rotation and revocation are administrative R2 operations and will require a
registered contract, recovery role, exact-plan confirmation, expiry,
tamper-evident audit and a dedicated credential provider before exposure.

### Device profiles

The simulator boots into `assistant`. The active profile is always exposed as a
visible indicator. Entering `lab` requires an unlocked device, operator
identity, active scope and expiry of at most 30 minutes. Reboot and expiry
return the simulator to `assistant`.

A signed device profile claim does not create server authorization. The
existing policy engine still evaluates the command profile, actor, device,
grant or scope and tool requirements.

### Structured text delivery

The simulated backend accepts a `text_command` only after protocol
authentication and schema validation. The authenticated device ID must match
both the execution context and the command's `source_device_id`. Envelope and
command timestamps must be identical, and the correlation ID must match the
command value or its command-ID default.

Dispatch is a closed branch over `camera.status`, `camera.monitor`,
`asset.list` and `network.passive_discovery`; no payload-provided name is
dynamically imported or executed. Each branch repeats tool-parameter
validation and uses its existing canonical target resolution, server-side
policy, idempotency and audit controls. Unknown actions are denied before a
service or worker starts.

This gateway consumes structured simulator fixtures. It does not interpret
free-form text and is not connected to the physical firmware's RAM-only local
draft. Adding a real transport or converting operator text into a registered
action remains separate work.

The simulator exposes a closed menu composer for `camera.status`,
`camera.monitor`, `asset.list` and `network.passive_discovery`. It accepts only
preloaded non-secret lists of at most 32 camera, eight inventory and eight
network/interface entries, applies the fixed required profile, bounds
monitoring and discovery parameters, and exposes the stored-inventory change
filter. These local lists are presentation state only: they neither enroll a
resource nor grant access, and the backend still resolves canonical ownership,
scope and authorization.

### Cancellation

A physical cancel input creates a signed, bounded `cancel_request`. After
transport verification, the backend resolves the exact job and invokes its
existing cooperative cancellation path. Cancellation messages cannot choose
arbitrary tools or parameters.

### Simulated push-to-talk

The simulator accepts one explicitly initiated capture at a time. It exposes a
visible microphone indicator and bounds a capture to 15 seconds and 18,000
encoded bytes. Cancellation or a limit violation clears the mutable buffer.
Successful processing always clears it. Audio retention is not implemented in
this simulator.

The voice payload uses Opus metadata for the intended transport contract. The
simulator does not encode or validate Opus, access a microphone, encrypt or
transmit the payload, or perform speech-to-text.

## Consequences

- Protocol and policy behavior can be tested without hardware or network I/O.
- Board differences are explicit before C++ code exists.
- The simulator must never be described as production-grade device identity.
- Identity lifecycle state, retired key IDs and secret-reuse fingerprints
  disappear on process restart.
- Real audio drivers and encoding, key storage, encrypted transport and
  firmware compilation remain future work.

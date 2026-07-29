# ADR-0012: Tomato Link RAM-only ephemeral bootstrap

- Status: Accepted
- Date: 2026-07-29

## Context

ADR-0011 models a dedicated Tomato Link root credential as if a successful
local provisioning ceremony had already installed it in two independent fake
vaults. Supplying the same bytes to both fakes does not prove how the endpoints
agree on those bytes without transmitting the resulting root or trusting an
unauthenticated network.

The original Cardputer has an ESP32-S3FN8 and USB Serial/JTAG. Its production
firmware target is Arduino-ESP32 3.3.10, based on ESP-IDF 5.5.4. ESP-IDF exposes
Curve25519 and RFC 5869 HKDF configuration options, but HKDF is disabled by
default. Firmware integration must therefore verify the resulting build
configuration rather than infer primitive availability from a framework
version.

## Decision

Add a simulation-only, RAM-only bilateral bootstrap with:

- fresh X25519 ephemeral key pairs on the Cardputer and edge;
- a strict `tomato-link-pairing-hello` v1 public contract;
- an exact organization, source endpoint, destination endpoint, ceremony and
  boot transcript;
- a 30-to-120-second ceremony window;
- a role-ordered canonical JSON transcript and SHA-256 transcript digest;
- a 128-bit, eight-group hexadecimal fingerprint shown identically on both
  displays;
- `physical_display` as the only accepted confirmation source;
- HKDF-SHA256 root derivation using the X25519 shared secret, the transcript
  digest as salt and a versioned Tomato Link context;
- independent confirmation and derivation at each endpoint;
- one-shot installation into separate credential providers;
- cancellation, expiry and reboot invalidation;
- sanitized status that contains no key material;
- a deterministic language-neutral interoperability fixture.

The root secret never crosses a contract. The public key, transcript digest
and display fingerprint are not credentials. Knowing them, reaching a
transport or replaying a hello does not enroll a device or authorize an
operation.

The simulator accepts a local credential sink. A successful call consumes the
root and clears the participant's references to its private key and derived
root. A failed sink call does not claim success and may be retried while the
ceremony remains live. A production sink must provide atomic install or
rollback; the simulator cannot manufacture that guarantee.

## Authorization and risk

Creating and comparing public bootstrap material is R0 foundation behavior.
Installing a credential on physical endpoints will be R2 because it changes
future trust. This ADR does not authorize or implement that physical write.

Pairing creates no role, profile, resource grant, operation scope, capability
or tool authorization. Normal server-side policy remains deny-by-default.

## Entropy requirement

Production firmware must generate the ephemeral private key from a source
meeting the ESP32-S3 hardware RNG prerequisites. `esp_fill_random()` is only
treated as a true-random source while an approved primary entropy source is
active. If Wi-Fi or Bluetooth is not active, firmware must follow the
documented bootloader entropy-source constraints or use a reviewed DRBG seeded
from true hardware entropy.

Deterministic private keys in the interoperability fixture are public test
data and must never be used for provisioning.

## Required negative controls

- unknown fields or malformed public keys;
- wrong role, organization, route or ceremony;
- reflected local public key;
- changed reuse of a received hello;
- expired, premature or overlong ceremony;
- non-physical confirmation source;
- mismatched fingerprint;
- root consumption before bilateral exchange and local confirmation;
- second root consumption;
- cancellation, expiry or reboot before consumption;
- secret fields in hello or status contracts;
- secrets in representations;
- pairing output that differs between endpoint implementations.

## Physical implementation boundary

This change adds no USB listener, serial command, firmware image, NVS entry,
flash write, eFuse change, secure-boot setting or network endpoint. The
Cardputer may remain in ROM download mode but is not accessed.

A future physical implementation requires a separate accepted decision and:

1. an exact local-only transport framing and payload cap;
2. explicit operator intent on both endpoints;
3. Cardputer UI that displays and confirms the complete fingerprint;
4. verified Curve25519/HKDF firmware configuration and the published vector;
5. measured RNG preconditions;
6. atomic installation or rollback;
7. secure at-rest storage, rotation, revocation and recovery;
8. power-loss tests and auditable state transitions;
9. an exact R2 confirmation before any device write.

## Consequences

The repository can now prove that two independent endpoints derive the same
Tomato Link root, install it into separate fake vaults and use the existing
short-lived AES-GCM session without sending the root.

This is not production provisioning. Python immutable byte copies cannot be
reliably zeroized, process memory is not a hardware-backed vault, physical
fingerprint comparison has not been exercised and the C++ vector has not yet
run on the original Cardputer.

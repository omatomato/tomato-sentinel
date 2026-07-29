# ADR-0013: Original Cardputer crypto interoperability evidence

- Status: Proposed
- Date: 2026-07-29

## Context

ADR-0012 requires verified Curve25519/HKDF firmware configuration and the
published pairing vector before a physical provisioning design can be
considered. The accepted firmware core is Arduino-ESP32 3.3.10, based on
ESP-IDF 5.5.4. That release contains the Espressif Mbed TLS fork at commit
`ffb280bb63c78bfec1e1ab55040671768c85c923`.

The pinned Mbed TLS configuration enables ECP, ECDH, Curve25519, the message
digest abstraction and SHA-256. Its standalone HKDF module is not enabled by
default. Adding or floating another cryptographic dependency would increase
the reviewed supply-chain surface without adding a missing primitive.

Compilation alone cannot establish entropy quality, physical behavior,
transport safety, operator confirmation or secure credential storage.

## Decision

Add an allocation-free C++ interoperability adapter that:

- imports RFC 7748 X25519 private scalars through the pinned Mbed TLS API;
- parses and validates peer Montgomery points before shared-secret
  computation;
- rejects a zero shared secret and clears outputs on all failures;
- computes SHA-256 over at most 2,048 exact transcript bytes;
- renders the first 128 digest bits as the ADR-0012 fingerprint;
- derives one 32-byte root using RFC 5869 extract-and-expand over the pinned
  HMAC-SHA256 implementation;
- uses the transcript digest as salt and
  `tomato-sentinel/tomato-link/ephemeral-root/v1` as exact HKDF info;
- requires the caller to inject the scalar-multiplication blinding RNG;
- keeps buffers bounded and explicitly clears secret intermediates.

Add a separate compile-only self-test image containing the public deterministic
fixture `tomato-link-pairing-v1`. It checks device and edge public keys, both
shared-secret directions, transcript digest, fingerprint and both derived
roots. It also checks rejection and output clearing for an all-zero low-order
peer and rejection of an oversized transcript.

The image is visibly marked `CRYPTO VECTOR`, `NO PAIRING / NO STORAGE` and
`COMPILE-ONLY`. It never initializes the keyboard, network, radio, storage or
credential path. Physical G0 cancellation remains the first ordinary loop
work. Logs expose only pass/fail status and the public vector identifier.

The special entry point requires both
`TOMATO_CRYPTO_INTEROP_SELF_TEST=1` and
`TOMATO_INTEROP_NON_DEPLOYABLE=1`, retains all existing runtime flash-write
guards and contains no upload command.

## Authorization and risk

This is R0 compile-time interoperability evidence. It registers no tool and
creates no role, profile, grant, scope, capability, confirmation or
credential. Deterministic code decides the checks; no model output is involved.

This decision does not authorize serial framing, USB commands, network
listeners, fingerprint approval, entropy acquisition, provisioning, flash,
NVS, eFuse or secure-boot changes. Those remain outside this implementation.

## Upstream intake

No new upstream package is added. The implementation uses only the approved
Arduino-ESP32 3.3.10 dependency already registered in
`config/upstream/software-catalog.yaml`. Review covered:

- the ESP-IDF 5.5.4 Mbed TLS configuration for Curve25519, ECDH and SHA-256;
- the exact Mbed TLS submodule commit used by that release;
- little-endian Montgomery key import and point serialization;
- public-key and zero-shared-secret rejection behavior;
- HMAC-SHA256 APIs used for an independent RFC 5869 implementation.

## Required controls

- Default firmware must not expose the deterministic fixture or self-test.
- The self-test build must fail unless marked non-deployable.
- Both build scripts must retain the original-board and runtime-write guards.
- Neither build script may contain an upload operation.
- The fixture bytes must match the language-neutral JSON fixture exactly.
- Oversized transcript and low-order peer controls must fail closed and clear
  outputs.
- Tests and logs must not expose generated or production credentials.

## Consequences

The repository can compile and independently compare the Python and firmware
cryptographic calculations without touching a Cardputer. It still cannot
claim that the vector ran on hardware, that a safe production RNG is wired, or
that physical pairing exists.

An accepted follow-up decision is still required before any R2 credential
installation design. That review must cover local framing, explicit bilateral
operator intent, full fingerprint confirmation, measured entropy
preconditions, atomic storage or rollback, rotation, revocation, recovery and
power-loss behavior.

## References

- [ESP-IDF 5.5.4 release](https://github.com/espressif/esp-idf/tree/v5.5.4)
- [Arduino-ESP32 3.3.10 release](https://github.com/espressif/arduino-esp32/tree/3.3.10)
- [RFC 7748](https://www.rfc-editor.org/rfc/rfc7748)
- [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869)

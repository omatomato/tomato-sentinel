# ADR-0008: Add a deterministic synthetic Spectra channel simulator

- Status: Accepted
- Date: 2026-07-26

## Context

The first `lab.spectra` executor returns a fixed fixture result. That proves the
authorization and state-machine path, but it cannot compare communication
models or measure error behavior.

Optical and acoustic covert channels can be used for prohibited exfiltration.
Tomato Sentinel must not accept arbitrary payloads, control real emitters,
capture real receivers or provide an executable path toward an unauthorized
target. Research adjacent to that boundary requires an explicit threat model
and human review.

## Proposed decision

Register `lab.spectra` version 2 as an R1, simulation-only edge module. Version
1 remains unchanged for compatibility.

Version 2 generates a synthetic payload from the immutable plan hash and
registered fixture identifiers. It creates a bounded frame, applies optional
extended Hamming(8,4), maps bits to synthetic ASK, FSK, Manchester or PWM
symbols, injects deterministic fixture noise and reports:

- transmitted synthetic samples;
- injected sample errors;
- channel and payload bit-error rates;
- corrected errors and uncorrectable blocks;
- frame synchronization and CRC32 status.

The module accepts no payload bytes, paths, endpoints, frequencies, pins,
devices or network destinations. `optical_fixture` and `acoustic_fixture` are
model labels only. The executor has no hardware, audio, radio, filesystem or
network adapter.

Existing laboratory controls remain mandatory: exact canonical fixture target,
`researcher` role, visible `lab` profile, operation scope, authenticated edge
capability, immutable plan hash, short-lived physical confirmation, finite
duration, maximum 65,536 payload bits, maximum 50 percent noise, cancellation
and complete audit.

## Consequences

- Channel behavior and error correction can be compared reproducibly without
  transmitting or capturing a physical signal.
- Version 1 plans retain their original schema and executor binding.
- Results are measurements of a model and are not evidence of physical range,
  reliability, detectability or Cardputer capability.
- A comparison runner may compose only a finite matrix of these same synthetic
  parameters.
- Any real sensor, emitter, microphone, display modulation, GPIO, radio or
  external process requires a separate accepted ADR, electrical/privacy review
  where applicable, exact target controls and new negative tests.

## Rejected alternatives

- Accepting operator-provided payload data: rejected because it creates an
  unnecessary exfiltration primitive.
- Reusing and breaking the version 1 manifest: rejected because registered
  plan schemas and executor bindings must remain stable.
- Adding physical I/O behind a simulation parameter: rejected because a
  parameter must never silently change the interaction boundary or risk.
- Calling a generated script or external modem tool: rejected because
  free-form execution and unregistered tools are prohibited.

## Review checklist

- Confirm the threat model in
  `docs/security/spectra-simulation-threat-model.md`.
- Confirm that both channel names remain synthetic fixtures.
- Confirm that arbitrary payloads and all physical/network adapters remain
  absent.
- Confirm positive, denial, maximum-boundary and cancellation coverage.

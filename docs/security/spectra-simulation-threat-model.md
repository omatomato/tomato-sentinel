# Spectra simulation threat model

## Scope

This threat model covers `lab.spectra` version 2 and
`executor:spectra-simulator-v2`. It covers deterministic in-memory generation,
framing, modulation, error injection, demodulation, Hamming decoding and
metrics. It does not authorize a physical optical, acoustic, electrical or
radio experiment.

## Protected boundaries

- The AI/model boundary may select only a registered proposal fixture.
- The plan binder supplies the actor, organization, device, canonical target,
  fixture identifiers, scope and time outside model output.
- The policy boundary requires the exact R1 module/version, trusted device,
  `researcher` role, `lab` profile, operation scope and physical confirmation
  bound to the immutable plan hash.
- The edge capability boundary binds execution to the exact registered
  executor and short-lived authenticated edge report.
- The executor boundary accepts only schema-validated scalar parameters and
  returns a schema-validated simulation result.

## Data

All processed bits are synthetic and deterministically derived from the plan
hash and registered fixture identifiers. The module accepts no user content,
file, secret, credential, personal identifier, capture or external evidence.
Results contain aggregate synthetic metrics only.

## Misuse cases and controls

### Arbitrary-data encoding

An operator or model attempts to encode supplied bytes, a file or a secret.

Control: the version 2 schema has no payload field and rejects unknown
properties. Trusted code creates the payload internally.

### Physical transmission or capture

An implementation attempts to bind `optical_fixture` or `acoustic_fixture` to
a display, LED, speaker, microphone, ADC, GPIO, radio or external program.

Control: the executor contains only in-memory standard-library computation.
The manifest requires no hardware, physical hardware profiles remain disabled
and no adapter interface is available.

### Parameter or resource exhaustion

An input requests excessive payload, noise, duration or output.

Control: payloads are limited to 8 through 65,536 bits, noise to 0 through 50
percent and duration to 1 through 120 seconds. The plan is size-bounded,
schema-validated and checked against the manifest. The largest FSK/Hamming
case produces 524,928 synthetic samples.

### Plan mutation after confirmation

The channel, modulation, FEC, noise or sample count changes after the operator
reviews the plan.

Control: every parameter is covered by the canonical plan hash. Physical
confirmation is valid only for that exact hash.

### Unregistered execution path

A caller selects a different function, executor string or dynamically loaded
module.

Control: module and executor registries use exact versioned bindings. The
engine dispatches only through its injected executor map and rejects missing
or duplicate identifiers.

### False physical claims

Synthetic BER is presented as observed performance of a Cardputer or real
channel.

Control: the manifest and every result require
`execution_mode: simulation`. Documentation states that the channel names are
models and results are not physical evidence.

## Negative controls

- Unknown channel, modulation and error-correction values are rejected.
- Payloads below 8 or above 65,536 bits are rejected.
- Noise outside 0 through 50 percent is rejected.
- Missing capability, scope or exact physical confirmation denies execution.
- A changed parameter invalidates the plan hash.
- Cancellation remains idempotent through the experiment engine.
- Result schema validation fails closed before a job can complete.

## Residual risk

The framing and coding concepts are general communications knowledge and could
inform a separate implementation. This repository limits that risk by
excluding arbitrary data, physical adapters and external execution. No claim
is made that this eliminates misuse outside Tomato Sentinel.

## Promotion criteria

This module may move beyond simulation only through a new threat model and
accepted ADR identifying exact owned hardware, electrical limits, privacy
classification, physical environment, target authorization, retention,
emergency cancellation and evidence requirements. R3 functionality remains
prohibited.

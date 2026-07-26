# Research lab platform

## Current status

The research-lab foundation is implemented as a simulation-only vertical
slice. It combines the Cardputer interface, a local edge boundary,
deterministic authorization and fixture-based experiment executors. It does
not open a network listener, initialize physical modules, transmit radio
frames, inject logs or access real captures.

The registered module line is:

- `lab.spectra` version 1, the retained fixture-only compatibility experiment;
- `lab.spectra` version 2, an R1 deterministic synthetic channel experiment;
- `lab.soc` version 1, an R1 synthetic SOC-detection experiment.

Both require the visible `lab` profile, the `researcher` role, an exact
operation scope, a short-lived authenticated edge capability report, finite
duration and sample limits, cancellation and audit. Results always include
`execution_mode: simulation`.

## Spectra channel simulation

`lab.spectra` version 2 turns the original fixed result into a bounded,
repeatable communication-channel simulation. The payload is generated from
the exact plan hash and registered fixture identifiers; arbitrary content is
not accepted. Trusted code then:

1. creates a frame with a fixed preamble, a bounded payload length and CRC32;
2. optionally applies extended Hamming(8,4) error correction;
3. maps encoded bits to ASK, FSK, Manchester or PWM synthetic symbols;
4. injects a finite deterministic error set for an optical or acoustic
   fixture;
5. demodulates, decodes and reports channel BER, payload BER, corrected
   errors, uncorrectable blocks, frame synchronization and checksum status.

Both channel names are models, not physical inputs. The executor imports no
network, audio, radio, GPIO or filesystem adapter. It never initializes the
registered hardware candidates and cannot transmit or capture a signal.
Payloads are limited to 65,536 bits, noise to 50 percent and execution to the
existing three cancellable engine steps. Version 1 remains registered so old
plans keep their original schema and executor binding.

The accepted decision and misuse analysis are in
`docs/decisions/ADR-0008-synthetic-spectra-channel-simulator.md` and
`docs/security/spectra-simulation-threat-model.md`.

## Execution flow

1. The local model provider returns a proposal matching the closed proposal
   schema. The current provider is a reviewed deterministic fixture.
2. Trusted code resolves aliases to an exact registered module, target and
   fixture; authenticated actor, organization, device, scope and time are
   added outside the model.
3. The complete plan receives a canonical hash and is validated again.
4. The experiment engine checks identity binding, scope lifetime, edge
   capabilities and deterministic policy.
5. An exact executor binding creates a cancellable session.
6. Every state transition is audited. Only a schema-valid final result can be
   marked completed.

The Cardputer dashboard is currently a simulator. It can display advertised
modules, exact-plan review, bounded progress, completion and cancellation. It
cannot create arbitrary commands.

The edge converts a validated capability report into a bounded `lab.modules`
view with named tiles and risk labels. Before a session can show as running,
the dashboard holds the exact experiment ID, target and fixture counts,
duration, sample count and plan hash. A physical confirmation is then required
for that exact hash.

## Signed dashboard path

The simulated Cardputer can now sign a `lab_dashboard_request` envelope before
asking the edge for capabilities or a reviewed proposal. The edge gateway
verifies the provisioned device identity, HMAC tag, replay controls, timestamp,
source device, correlation identifier, `lab` profile and closed action map
before calling the local application.

This is simulation HMAC, not production transport cryptography. The edge
response is an in-process result and is not represented as a signed network
message. There is still no listener, socket, LAN traffic or experiment-start
method in this path.

## Physical start confirmation

Both initial R1 modules require a physical confirmation. The Cardputer sends a
signed `lab_plan_confirmation` containing the exact plan hash, source device,
bound operator, scope and timestamp. The edge verifies the envelope and its
operator binding, then issues a policy confirmation valid for 60 seconds.
Changing any plan field changes its hash and invalidates that confirmation.

The current physical key is simulated: no firmware input or hardware GPIO was
changed. This preserves the exact same policy path while the original
Cardputer's physical UI integration is designed and reviewed.

## Local edge boundary

The edge application exposes only three in-process methods:

- `edge.health`;
- `edge.capabilities`;
- `experiment.propose` with a reviewed prompt identifier.

It requires a transport-authenticated peer context, checks organization
binding, bounds payloads and retains bounded idempotency records. No transport
adapter or listener exists yet. Adding one requires an ADR for authenticated
encryption, replay protection, certificate rotation and exposure rules.

## Physical module candidates

The nRF24L01, CC1101, PN532 and photodiode profiles are declarative candidates
only. Their schemas require all of the following:

- activation disabled;
- wiring and pins unassigned;
- driver not integrated;
- transmit and write permission false;
- electrical review pending;
- hardware test false.

Registration therefore provides planning visibility but no executable
capability. Each future activation needs exact original-Cardputer wiring,
voltage/current review, upstream intake, a risk decision, negative controls
and an authorized hardware test.

## Next safe increment

The next increment should add a comparison runner that produces a bounded
matrix across the registered synthetic channels, modulations, noise levels and
error-correction modes. A real local model runtime, network transport or
physical module should be introduced only after its separate provider,
transport or hardware decision is accepted.

# Tomato Sentinel

Tomato Sentinel is a privacy-conscious AI, automation, physical-monitoring,
asset-visibility and authorized cybersecurity platform built around M5Stack
Cardputer devices, edge nodes and backend services.

The Cardputer is a portable interface and field terminal. It captures bounded
push-to-talk audio, accepts keyboard input, displays alerts, exposes verified
hardware capabilities and provides physical confirmation. Expensive speech,
language-model and computer-vision processing runs on authorized edge or
backend infrastructure.

## Status

Tomato Sentinel is in its simulated vertical-slice phase. The repository
defines the product boundaries, architecture, authorization model, risk policy,
privacy baseline and upstream-software governance. It also contains the first
policy-engine core, JSON Schema contracts, an R0 `camera.status` flow and the
complete simulated R1 `camera.monitor` MVP. The R1 path uses bounded fake
frames, temporal person confirmation, cancellation, idempotent notification
and a simulated Cardputer inbox. No real camera or network access, security
tool or production service is implemented yet. A Cardputer protocol simulator
now covers explicit original/Adv board profiles, authenticated envelopes,
capability reports, replay protection, visible profiles and physical
cancellation. The original Cardputer is the primary MVP hardware target; Adv
is retained only as an explicit future-compatibility profile. Bounded
push-to-talk capture is simulated without microphone or network access.
Reviewed audio fixtures can now traverse a deterministic simulated
speech-to-text and exact-intent path into the existing authorized
`camera.monitor` workflow. A separate R0 `asset.list` slice reads only
pre-registered in-memory inventory and returns sanitized changes without
network discovery. Bounded R1 passive discovery is now simulated with exact
network scope, candidate limits and cancellation, but opens no socket and
cannot enroll a discovered device. A simulation-only research-lab foundation
now adds versioned module manifests, hashed experiment plans, an audited
execution state machine, short-lived edge capability reports, fixture-only SOC
and compatibility modules, a deterministic Spectra v2 channel simulator, a
simulated Cardputer dashboard and a structured local-AI proposal boundary.
Spectra v2 provides bounded synthetic framing, ASK/FSK/Manchester/PWM
modulation, optional Hamming(8,4), deterministic noise and BER/checksum
metrics. It opens no physical, audio or network adapter. The local edge
application has no network listener or execution endpoint. Physical
nRF24L01, CC1101, PN532 and photodiode profiles are registered only as
disabled, unwired and untested candidates. The simulated Cardputer dashboard
can now make a signed, replay-protected request for edge capabilities or a
reviewed proposal. The first simulated R1 modules also need a short-lived,
signed physical-confirmation event bound to the exact plan hash before the
engine may start them. Tomato Link now has a bounded in-memory relay, a
fail-closed outbound WSS client boundary and PC-side AES-256-GCM payload
sealing with authenticated routing metadata. It still has no public listener,
configured relay, production credential provider or physical Cardputer key
provisioning. A proposed session-governance slice now adds separate simulated
link credentials, authenticated short leases, HKDF-derived keys, immediate
rotation/revocation invalidation and an independent encrypted physical-cancel
lane that remains available when the ordinary relay queue is full.

## Core principle

> AI may propose registered operations. Deterministic code decides whether an
> operation is allowed.

Natural-language output is never executed directly.

## Documentation

- [Product vision](docs/product/vision.md)
- [First MVP](docs/product/mvp.md)
- [System architecture](docs/architecture/system-architecture.md)
- [Authorization model](docs/security/authorization-model.md)
- [Tool risk model](docs/security/tool-risk-model.md)
- [Privacy and data governance](docs/privacy/data-governance.md)
- [Upstream-software policy](docs/governance/upstream-software.md)
- [Development workflow](docs/operations/development-workflow.md)
- [Language and toolchain decision](docs/decisions/ADR-0002-language-toolchain-and-contracts.md)
- [Simulated device protocol decision](docs/decisions/ADR-0003-simulated-device-protocol.md)
- [Simulated voice pipeline decision](docs/decisions/ADR-0004-simulated-voice-command-pipeline.md)
- [Stored asset inventory decision](docs/decisions/ADR-0006-stored-asset-inventory-slice.md)
- [Simulated passive discovery decision](docs/decisions/ADR-0007-simulated-passive-discovery.md)
- [Proposed synthetic Spectra decision](docs/decisions/ADR-0008-synthetic-spectra-channel-simulator.md)
- [Spectra simulation threat model](docs/security/spectra-simulation-threat-model.md)
- [Tomato Link foundation decision](docs/decisions/ADR-0009-tomato-link-remote-transport-foundation.md)
- [Secure Tomato Link decision](docs/decisions/ADR-0010-tomato-link-secure-session-and-wss.md)
- [Tomato Link threat model](docs/security/tomato-link-threat-model.md)
- [Proposed Tomato Link session governance decision](docs/decisions/ADR-0011-tomato-link-session-governance-and-cancellation.md)
- [Tomato Link session governance threat model](docs/security/tomato-link-session-governance-threat-model.md)
- [Research lab platform](docs/product/research-lab-platform.md)
- [Local edge boundary](services/edge-agent/README.md)
- [Local edge lab console](apps/edge-lab-console/README.md)
- [Simulated orchestrator slice](services/orchestrator/README.md)
- [Original specification snapshot](docs/product/product-specification-original.md)

Repository-wide agent and contributor constraints are in [AGENTS.md](AGENTS.md).

## Planned repository layout

```text
firmware/cardputer/       Cardputer firmware and board profiles
apps/api/                 public/control API
apps/operator-console/    operator interface
apps/mobile/              mobile client
services/edge-agent/      disabled-by-default local edge application boundary
services/                 bounded backend services
packages/contracts/       shared commands, events and schemas
packages/experiment-engine/ versioned modules, plans and state machine
packages/policy-engine/   deterministic authorization
packages/scope/           canonical scopes and resource grants
integrations/             isolated external adapters
config/                   reviewed declarative configuration
infra/                    deployment, provisioning and observability
tests/                    integration, end-to-end, security and simulation
```

Directories will be introduced with their first owned artifact rather than as
empty placeholders.

## Development

The initial backend workspace supports Python 3.13 and 3.14 and uses uv
`0.11.29`.

```text
uv sync --locked --all-groups
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

Dependencies and CI actions are pinned and registered in
`config/upstream/software-catalog.yaml`. The current Python development SBOM is
stored in `sbom/python-development.cdx.json`.

## Security

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

## License

No open-source license has been selected. The repository is private and no
permission to copy, redistribute or reuse its contents is granted at this
stage. Upstream projects retain their own licenses.

# Tomato Sentinel agent guidance

This file contains repository-wide instructions for humans and coding agents.
Read it before making changes. Then read the nearest nested `AGENTS.md`, when
one exists.

The original project specification is preserved without edits at
`docs/product/product-specification-original.md`. Focused documents and
accepted ADRs take precedence where they intentionally clarify or replace its
wording. Requirements in the snapshot remain normative for subjects not yet
covered by a focused document. Read the relevant snapshot section before
changing such a subsystem; do not load it for unrelated work.

## Project purpose

Tomato Sentinel is a modular, privacy-conscious platform combining:

- an AI assistant;
- authorized physical monitoring;
- asset visibility;
- a bounded, authorized security laboratory;
- M5Stack Cardputer devices as portable interfaces and field terminals.

Heavy language-model, speech and vision processing belongs on an authorized
edge node, backend, or configured provider. Firmware must use explicit board
profiles and hardware capability detection.

## Invariants

These rules are non-negotiable:

1. AI may propose registered actions. Deterministic code decides whether they
   are allowed.
2. Never execute free-form model output, arbitrary shell text, generated HID
   payloads, or unregistered tools.
3. Authorization is deny-by-default and enforced server-side.
4. Discovery does not enroll, trust, authenticate, or authorize a target.
5. Credentials remain isolated from discovery records, public APIs, logs,
   notifications, evidence exports, and separate firmware images.
6. Sensitive work is bounded by canonical targets, finite duration, resource
   limits, cancellation, audit and, when required, physical confirmation.
7. R3 operations are not executable, registrable, or AI-proposable in Tomato
   Sentinel.
8. Never weaken policy, scope, tenant isolation, confirmation, redaction or
   audit controls to simplify an implementation.
9. Never claim that an operation ran when it was planned, denied, simulated,
   cancelled or not tested.
10. Do not copy or execute upstream code without completing the declared
    upstream intake workflow.

## Canonical authorization model

Keep these concepts distinct:

- **role**: the operator's administrative and business permissions;
- **profile**: the visible, temporary operating mode of a device;
- **resource grant**: normal access to a registered camera, sensor or asset;
- **operation scope**: time-bounded authorization for inventory or laboratory
  operations against canonical targets;
- **capability**: trusted hardware or service functionality;
- **risk class**: the intrinsic risk of a registered tool;
- **confirmation**: a short-lived approval for one exact plan;
- **obligation**: a limit or control attached to an allow decision.

Every policy decision must evaluate the actor, organization, device identity
and posture, profile, resource grant or operation scope, verified capability,
registered tool, canonical targets, parameters, environment and confirmation.

See `docs/security/authorization-model.md`.

## Risk classes

- **R0 — read-only**: reads existing authorized state.
- **R1 — bounded observation**: finite monitoring or scoped observation.
- **R2 — active/state-changing**: exact target, stronger role/profile,
  confirmation, short expiry and complete audit.
- **R3 — prohibited**: jamming, credential theft or stuffing, third-party
  camera access, autonomous exploitation, persistence, destructive payloads,
  arbitrary HID, undefined targets and similar functionality.

R3 entries must never appear as executable tools. Research adjacent to R3
requires a separate threat model, ADR and human review before any prototype.

See `docs/security/tool-risk-model.md`.

## Execution boundaries

Prefer:

- **Cardputer** for UI, push-to-talk, directly connected modules and physical
  confirmation;
- **edge agent** for multicast discovery, camera connectivity, local vision,
  packet capture and protocol normalization;
- **backend** for orchestration, policy, scope, inventory, external
  intelligence, notifications, evidence and audit;
- **isolated external service** for NVRs, home automation, model servers,
  databases and large upstream applications.

Business logic depends on internal contracts, not directly on an upstream API.
Shared schemas belong in `packages/contracts`; shared authorization logic
belongs in `packages/policy-engine`.

See `docs/architecture/system-architecture.md`.

## Security and privacy baseline

- Use per-device identities with revocation and rotation.
- Require authenticated encryption, replay protection and payload limits.
- Treat firmware trust, signed updates and rollback protection as foundation
  work, not late hardening.
- Store secrets in a dedicated credential provider or encrypted vault.
- Apply outbound destination controls and explicit SSRF protections.
- Classify audio, images, identifiers, radio captures and evidence before
  storage or provider transfer.
- Default to short retention and no continuous cloud recording.
- Keep biometric identification outside the MVP.
- Use tamper-evident, access-controlled audit storage.

See `docs/privacy/data-governance.md` and `SECURITY.md`.

## Upstream software

Every researched or integrated upstream project must be registered in
`config/upstream/software-catalog.yaml` with an exact release, tag or commit
before approval.

Allowed integration modes are:

- `reference_only`;
- `independent_reimplementation`;
- `native_library`;
- `vendored_component`;
- `external_service`;
- `firmware_image`;
- `remote_adapter`.

Never install from a URL pipe, use floating production dependencies, accept
unreviewed binaries, silently add network destinations, add unjustified
privilege, or copy code without provenance and license review.

See `docs/governance/upstream-software.md`.

## Before changing code

1. Read this file and the nearest nested `AGENTS.md`.
2. Inspect the current architecture and working tree.
3. Identify affected trust boundaries and data classes.
4. Declare the tool risk class, if executable behavior changes.
5. Identify the required role, profile, grant/scope and confirmation.
6. Define positive tests and at least one relevant negative control.
7. Make the smallest complete change.

## During implementation

- Validate all external input at runtime.
- Keep transport models separate from domain models.
- Use structured, versioned contracts.
- Use finite timeouts, bounded retries and bounded buffers.
- Preserve cancellation and idempotency.
- Keep network access out of ordinary unit tests.
- Use fake adapters for external services and unavailable hardware.
- Avoid unrelated refactors.
- Redact secrets and unnecessary personal data.
- Document any check that is not applicable instead of silently omitting it.

## After implementation

Run the repository-provided formatting, lint, type-check and relevant test
commands. Also:

1. verify negative controls;
2. inspect logs and fixtures for secrets;
3. review the final diff;
4. report commands actually executed;
5. report checks that could not run.

Until language toolchains are selected, follow
`docs/operations/development-workflow.md`.

## Definition of done

A change is complete when all controls applicable to that change are
implemented and verified. Mark non-applicable controls explicitly; do not
pretend every R0 backend query requires hardware or cancellation.

Executable features additionally require:

- registered and versioned tool contracts;
- validated inputs and canonical targets;
- server-side authorization;
- declared risk and execution location;
- bounded resources and timeout;
- cancellation where execution can outlive a request;
- idempotent events and side effects;
- auditable state transitions;
- positive tests and denial tests;
- updated operator-visible documentation.

## Initial delivery order

1. **Foundation**: repository governance, contracts, authorization model,
   policy engine, registry, state machine, fakes, CI and supply-chain controls.
2. **Simulated MVP vertical slice**: structured text command through policy,
   fake camera monitoring, event deduplication and fake notification.
3. **Cardputer core**: board profiles, push-to-talk, transport, identity,
   profile indicator and cancellation.
4. **Camera sentinel**.
5. **Asset inventory**.
6. **Read-only hardware laboratory**.
7. **Controlled R2 tools**, only after policy and negative tests are mature.

The first acceptance target is documented in `docs/product/mvp.md`.

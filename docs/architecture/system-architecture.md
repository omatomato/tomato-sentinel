# System architecture

## Design goals

- deterministic authorization around all executable behavior;
- explicit placement according to compute, privacy and hardware needs;
- stable internal contracts around replaceable providers;
- operation without production credentials in development;
- bounded work with cancellation, idempotency and audit;
- explicit support for multiple Cardputer board profiles.

## Components

### Cardputer firmware

Owns:

- board profile and trusted hardware detection;
- keyboard, display, speaker and bounded push-to-talk;
- device identity and authenticated transport;
- visible operating profile and active-operation indicators;
- directly connected modules;
- physical confirmation and emergency cancellation.

It does not own policy truth, organization authorization, heavy speech, LLM or
vision inference.

### Edge agent

Owns local operations that benefit from LAN or device proximity:

- multicast discovery;
- camera connectivity;
- local motion and object detection;
- protocol normalization;
- explicitly authorized packet capture;
- bounded access to edge-connected hardware.

The edge agent is independently identified, scoped and revocable. It is not an
implicitly trusted backend extension.

### Backend

Owns:

- command orchestration and target resolution;
- tool registry and deterministic policy;
- resource grants and operation scopes;
- job state machines;
- asset inventory and external intelligence;
- notifications;
- evidence and audit.

### Isolated external services

Large upstream applications run as separate, least-privilege processes or
containers behind an internal adapter. Credentials remain with the responsible
adapter.

## Trust boundaries

```text
operator
    -> Cardputer or operator console
        -> authenticated device/API boundary
            -> orchestrator and policy boundary
                -> job execution boundary
                    -> edge, provider or isolated upstream
                        -> external device/network boundary
```

Every boundary validates identity, version, size and authorization context.
Provider output and discovery responses are untrusted input.

## Shared contracts

Versioned contracts belong in `packages/contracts` and include:

- command and result envelopes;
- tool manifests;
- policy request and decision;
- job and transition events;
- discovery candidates;
- camera and detection events;
- notification requests;
- audit events;
- signed capability reports.

All messages include a protocol version, message ID, timestamp, correlation ID,
producer identity and payload type. Replay windows and clock-skew handling must
be explicit.

## Internal adapter contract

Each upstream adapter exposes equivalent operations:

```text
health
capabilities
validate_configuration
execute
cancel
```

The transport may be Python, TypeScript or another implementation language;
the source of truth is a language-neutral schema, not a Python protocol alone.

## Job lifecycle

```text
created
  -> validated
  -> authorized
  -> awaiting_confirmation (when required)
  -> running
  -> completed | cancelled | expired | failed
```

Validation or authorization may terminate at `denied`. Invalid transitions fail
explicitly. Replayed requests reuse the original result or conflict safely;
they do not create duplicate workers.

## Outbound network policy

Network-capable adapters require:

- explicit destination classes or allowlists;
- scheme and port restrictions;
- DNS resolution and rebinding defenses;
- redirect validation;
- private/link-local/metadata-address handling;
- finite connect/read timeouts;
- response-size limits;
- proxy behavior documented;
- sanitized request and response evidence.

Camera-supplied URLs and upstream redirects are never trusted automatically.

## Degraded operation

When the backend is unavailable, the Cardputer:

- displays disconnected state;
- permits only documented local R0 shortcuts;
- does not invent authorization or extend expired laboratory state;
- queues no sensitive action without bounded, replay-safe semantics;
- retains the emergency cancellation path for locally running work.

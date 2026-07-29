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

For future remote Cardputer operation, the edge agent initiates an outbound
Tomato Link connection. It does not require a public inbound port on the
operator's PC. The provider-neutral relay core opens no network listener. The
edge WSS boundary and PC-side payload sealing are implemented but have no
configured public destination or production credentials; ADR-0009, ADR-0010
and the Tomato Link threat model record the remaining blockers.

### Tomato Link relay

The relay routes short-lived opaque frames between one authenticated Cardputer
endpoint and one authenticated edge endpoint in the same organization. It does
not inspect or execute inner commands and cannot grant authorization.

Both endpoints are expected to initiate outbound connections so that a
Cardputer using a phone hotspot can reach an edge node behind NAT or CGNAT.
The proposed sealed payload provides end-to-end authenticated encryption for
inner content because TLS terminated at the relay cannot protect content from
the relay operator. Production use additionally requires accepted physical key
provisioning, durable replay state, relay authentication and operational
controls.

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

### Future mobile camera source

A phone camera may later be enrolled as an authorized, temporary video source.
Reliable capture will probably require a companion mobile client; a foreground
browser client may be evaluated for a narrower prototype. The implementation
choice requires a separate threat model and ADR and is outside the first MVP.

The phone device identity, camera resource enrollment and viewing grant remain
separate. Installing or discovering the client grants none of them. Capture
requires operating-system permission, an explicit operator start, a persistent
on-device indicator, a finite session and immediate local cancellation. The
backend must not silently activate a phone camera.

Mobile frames and audio are sensitive data. Transport requires authenticated
encryption and bounded destinations, local or edge inference is preferred, and
continuous cloud recording remains disabled by default. Retention, provider
transfer and evidence export require explicit classification and audit.
Biometric identification remains outside the MVP.

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

Remote transport adds an untrusted relay between the authenticated device/API
boundary and the edge. Relay acceptance means only `queued`; the edge still
authenticates the inner device envelope before replay mutation or policy use.

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
- signed capability reports;
- normalized speech transcriptions.

All messages include a protocol version, message ID, timestamp, correlation ID,
producer identity and payload type. Replay windows and clock-skew handling must
be explicit.

ADR-0003 defines the protocol-v1 simulator and its deliberately non-production
HMAC identity boundary.

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

# Tomato Link threat model

## Scope

This threat model covers the proposed remote path:

```text
original Cardputer
    -> hotspot or Wi-Fi
        -> untrusted internet
            -> Tomato Link relay
                -> outbound edge-agent connection
                    -> policy and orchestration
```

The current code covers only the in-memory relay core and outbound-client state
machine. It opens no socket and provides no production confidentiality.

## Protected assets

- per-device and edge identity keys;
- inner authenticated device envelopes;
- command, audio, result and cancellation content;
- organization and endpoint isolation;
- replay and idempotency state;
- policy decisions, confirmations and audit events;
- availability of local physical cancellation.

Payloads may contain sensitive audio, identifiers or operational data. Relay
metadata exposes at least endpoint relationships, timing and sizes even after
future end-to-end encryption.

## Adversaries

- an unauthenticated internet client;
- an authenticated but compromised endpoint;
- a malicious or compromised relay operator;
- a cross-organization tenant;
- an on-path observer or packet modifier;
- an attacker replaying, reordering, delaying or flooding frames;
- a stolen or revoked Cardputer;
- a malicious Wi-Fi access point or phone hotspot.

## Trust boundaries and controls

### Endpoint authentication

The relay must receive an authenticated principal from a future transport
adapter and bind it to one endpoint, organization and role. Caller-supplied
frame fields cannot change that binding. Unknown, disabled, cross-organization
and same-role routes fail closed.

The simulation models this with `AuthenticatedRelayPeer`; it is not evidence
of production authentication.

### Payload confidentiality and integrity

Base64 is not encryption. The current simulation validates only decoded size
and SHA-256 consistency and must remain local.

Production requires reviewed end-to-end authenticated encryption between the
Cardputer and its bound edge node. TLS to the relay alone is insufficient
because it permits relay plaintext access. Nonces, algorithms, key IDs and
rotation semantics require a separate accepted ADR. Authentication must occur
before replay state changes.

### Replay, ordering and expiry

Frames have short expiry, a unique frame ID and a monotonic sequence scoped to
source endpoint and session. Exact retransmission is idempotent; changed reuse
of a frame ID and non-increasing sequences are denied. Production state must
survive process restarts and use bounded storage.

Clock failure must show a disconnected state and deny sensitive work; it must
not silently widen the replay window.

### Resource exhaustion

Decoded payloads, encoded envelopes, TTL, queues, queued bytes, pulls,
idempotency records, connection attempts and backoff are bounded. Full queues
reject new traffic instead of silently dropping existing frames.

Public deployment additionally requires per-principal rate limits, connection
caps, global capacity protection and safe overload responses.

### Authorization separation

Delivery grants no permission. The relay cannot register tools, select dynamic
actions or mark work complete. The receiving edge verifies the inner device
envelope and calls deterministic policy and explicit action maps.

Discovery, connectivity and possession of a relay identity do not enroll a
resource or create a grant, scope, profile, role or capability.

### Cancellation and degraded operation

G0 retains local priority regardless of network state. A disconnected
Cardputer displays that state and cannot assume cached authorization.

Because an encrypted relay cannot safely infer inner message meaning, a future
authenticated control lane must carry bounded cancellation metadata without
allowing arbitrary priority traffic. Until that design is accepted, remote
cancellation is not production-ready.

## Required negative controls

- unauthenticated peer;
- disabled or unknown endpoint;
- forged source binding;
- cross-organization destination;
- device-to-device or edge-to-edge route;
- changed frame with reused ID;
- non-increasing sequence;
- stale, future or overlong expiry;
- invalid base64, size or digest;
- oversized payload, queue and pull;
- acknowledgement by the wrong endpoint;
- missed heartbeat, reversed clock and retry exhaustion;
- revoked physical device identity before inner dispatch.

## Out of scope for this foundation

- public listener and DNS;
- production TLS or WebSocket adapter;
- end-to-end encryption and provisioning;
- relay persistence and multi-node consistency;
- audio upload and model-provider transfer;
- physical Wi-Fi firmware;
- mobile camera sources;
- execution of any inner tool.

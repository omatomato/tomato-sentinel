# Tomato Link session governance threat model

## Scope

This model covers simulation-only root credentials, authenticated short-lived
session leases, derived AES keys and the independent physical-cancellation
lane. It extends the broader Tomato Link threat model.

No public listener, physical provisioning write or persistent credential store
is included.

## Protected assets

- dedicated per-route Tomato Link root secrets;
- derived AES-256 session keys;
- key IDs and identity revisions;
- lease authentication and replay state;
- exact cancellation job binding;
- availability and latency of physical cancellation;
- separation from device-message authentication credentials.

## Trust boundaries

### Fake credential vault

The in-memory vault stands in for two independent endpoint credential
providers. It accepts a root secret only for one exact organization, source
and destination route. Status and representations expose metadata but never
secret bytes.

The same root material is needed at both endpoints in simulation. In
production it must arrive through an authenticated local ceremony and be
stored independently. The relay never receives it.

### Session lease

A lease carries only route metadata, key identity and a random salt. HMAC
authenticates every field before acceptance mutates replay state. HKDF binds
the derived key to the route, lease, session, key ID and revision.

An accepted lease remains usable only while its time window and credential
revision are current. Rotation or revocation invalidates it immediately at
the managed-session boundary.

### Priority cancellation

The relay recognizes only enough outer metadata to place a fixed
`physical_cancel` frame in a separate bounded queue. AES-GCM authenticates that
metadata together with the sealed inner signed device envelope.

The edge checks:

1. current session validity;
2. AES-GCM authentication;
3. device-envelope authentication and replay;
4. fixed `cancel_request` schema and physical input source;
5. equality of outer and inner job IDs;
6. execution-context device identity;
7. existing job cancellation state machine.

Acknowledgement means removal from the relay queue, not successful job
cancellation.

### Operator-visible state

Transport connectivity alone is not a security state. The sanitized status
contract couples the `LINK: SECURE` indicator to current end-to-end encryption,
credential revision and cancellation readiness. Missing or expired controls
produce `LINK: DEGRADED`; revocation overrides a connected transport.

## Adversaries and controls

### Malicious relay

The relay can drop, delay, reorder or withhold frames. It cannot read the
sealed cancellation, change its job binding or create a valid new control.
Local G0 cancellation remains authoritative when connectivity fails.

### Compromised endpoint

A compromised endpoint with a current root secret can derive session keys for
valid leases on its own exact route. Rotation and revocation limit future use
but cannot undo compromise before detection. Production hardware storage and
remote attestation remain unresolved.

### Queue exhaustion

Ordinary frames and controls use separate queues and byte limits. Filling the
ordinary queue does not consume control capacity. The control lane itself has
strict frame, byte, TTL and pull bounds; an authenticated compromised device
can still exhaust its own lane, so production requires scheduling fairness,
per-principal rate limits and latency monitoring.

### Replay and rollback

Lease IDs, control IDs and session sequences are monotonic or idempotent only
for exact retransmission. Key revisions and retired key IDs prevent rollback.
All current state is process-local; restart-safe persistence remains a
production blocker.

## Data classification

Root secrets and derived keys are credentials and must never cross contracts,
logs, audit events, notifications or evidence exports. Salts, key IDs and
route metadata are sensitive operational metadata. The sealed cancellation
contains an operational job identifier but no arbitrary command.

## Required tests

- identical endpoint derivation with separate vault instances;
- lease authentication before replay mutation;
- expiry, rotation and revocation invalidation;
- root-secret uniqueness and redaction;
- ciphertext and outer-binding tamper rejection;
- fixed control type and device-to-edge direction;
- cross-organization and role denials;
- independent cancellation availability under full ordinary queue;
- signed inner cancellation reaching exactly one running job.

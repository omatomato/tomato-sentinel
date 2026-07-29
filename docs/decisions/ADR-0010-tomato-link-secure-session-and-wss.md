# ADR-0010: Tomato Link secure session and outbound WSS

- Status: Accepted
- Date: 2026-07-29

## Context

ADR-0009 created a bounded relay core but deliberately provided no
confidentiality or network adapter. A remote Cardputer and an edge PC will
normally be on different networks, frequently behind NAT or CGNAT. Both
endpoints therefore need outbound connectivity to a relay, while the relay
must not receive command, audio or result plaintext.

TLS to a relay protects traffic from an on-path observer but does not protect
content from the relay operator. A second authenticated-encryption layer is
required between each device and its bound edge endpoint.

The physical original Cardputer does not yet have an approved durable-key
provisioning and recovery workflow. Burning eFuses is irreversible and is not
authorized by this decision.

## Decision

Introduce two independent layers:

1. an outbound WebSocket adapter that accepts only `wss://`, an exact host
   allowlist, certificate and hostname verification, TLS 1.2 or newer, bounded
   messages and queues, finite timeouts, disabled compression and no ambient
   proxy discovery;
2. an inner `tomato-link-sealed-payload` v1 envelope using AES-256-GCM with a
   fresh 96-bit random nonce and canonical outer routing metadata as
   authenticated associated data.

Session keys are exactly 256 bits and are bound to one organization, source,
destination and session. The key type redacts material from representations.
This change defines no file, environment-variable or firmware key store.
Callers must obtain a key from a future credential provider. A session sealer
rejects detected nonce reuse and stops after 1,024 messages rather than
silently exceeding its in-memory collision guard.

The relay continues to validate and route only the outer frame. It receives the
sealed envelope as opaque bytes and has no API for a session key. Delivery does
not authenticate, authorize or execute the inner request.

The Python edge and relay use exact releases:

- `cryptography==49.0.0` for AES-GCM;
- `websockets==16.1.1` for the outbound WSS client.

Both are registered in the upstream catalog and locked with artifact hashes.
The future ESP32-S3 implementation will use the Mbed TLS stack supplied by the
exact approved ESP-IDF/Arduino core rather than importing an unreviewed Noise
implementation or writing a new cipher.

## Authorization and risk

Opening a bounded authenticated transport is R0/R1. It creates no role,
profile, grant, operation scope, capability or confirmation. The inner
registered tool retains its own risk class and still passes through device
authentication, replay validation, deterministic policy and explicit action
maps.

No R2 action is added by this change. R3 remains unregistrable and
unexecutable.

## Required controls

- strict schema and rejection of unknown fields;
- ciphertext and routing-metadata tamper rejection;
- key/organization/source/session/destination binding;
- nonce length, uniqueness guard and session message cap;
- empty and oversized plaintext rejection;
- exact WSS destination allowlist;
- certificate and hostname verification;
- no URI user information, plaintext WebSocket or ambient proxy;
- bounded connection, heartbeat, message and queue resources;
- secrets redacted from representations and absent from contracts.

## Remaining production blockers

This decision does not authorize a public relay or a physical firmware write.
Before either:

1. specify physical key generation, provisioning, rotation, revocation,
   recovery and secure-at-rest storage;
2. authenticate relay peers without bearer credentials embedded in firmware;
3. add durable replay/idempotency state and cluster consistency;
4. create a starvation-resistant authenticated cancellation lane;
5. approve a relay host, certificate lifecycle, DNS/rebinding controls, rate
   limits, monitoring and incident response;
6. complete original Cardputer Wi-Fi power, thermal, disconnect and recovery
   tests;
7. verify an interoperable AES-GCM test vector on ESP32-S3 against the Python
   implementation.

## Consequences

The PC now has a concrete fail-closed WSS client boundary and can prove that an
opaque relay cannot read or silently modify a payload. Tests remain local and
use synthetic keys; no internet service or hardware is required.

The remote Cardputer feature is still not complete. In particular, ciphertext
without trustworthy physical key provisioning would only move the secret
problem elsewhere, so firmware networking remains blocked until that lifecycle
is accepted.

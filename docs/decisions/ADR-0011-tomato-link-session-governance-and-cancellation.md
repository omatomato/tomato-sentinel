# ADR-0011: Tomato Link session governance and priority cancellation

- Status: Proposed
- Date: 2026-07-29

## Context

ADR-0010 added end-to-end payload sealing and a fail-closed outbound WSS
boundary. Supplying an AES key directly was sufficient to verify encryption,
but not to model how a remote Cardputer session starts, expires, rotates or
stops trusting a compromised credential.

The ordinary relay queue is intentionally bounded. Physical cancellation
cannot depend on space remaining in that queue because an overload or a burst
of ordinary traffic could delay the safety control it is meant to invoke.

The existing device-message credential and the Tomato Link encryption
credential serve different purposes. Reusing one secret for both would couple
rotation domains and increase the effect of a compromise.

## Decision

Add a simulation-only session-governance layer with:

- one dedicated Tomato Link root credential per exact organization,
  Cardputer and edge route;
- root secrets separated from device-message authentication secrets;
- unique secret fingerprints across routes in one vault;
- explicit key IDs, identity revisions, rotation and terminal revocation;
- retired key IDs that cannot be reused;
- authenticated `tomato-link-session-lease` v1 contracts;
- HKDF-SHA256 derivation of a unique 256-bit AES session key using a fresh
  256-bit salt and canonical route/session context;
- lease duration from 10 through 120 seconds;
- exact idempotency and bounded lease records;
- immediate invalidation of an existing managed session after root rotation or
  revocation;
- no root secret, derived key or salt in representations, status models or
  logs.

The lease authentication algorithm remains
`simulation_hmac_sha256`. Authentication is checked before replay or
idempotency state changes. This is not production device identity and is not
presented as one.

Add a separate physical-cancellation lane with:

- a strict `tomato-link-cancel-frame` v1 contract;
- only `physical_cancel` as the accepted control type;
- device-to-edge routing only;
- a maximum 2 KiB sealed payload and 30-second lifetime;
- independent limits of 16 frames and 32 KiB per destination;
- a bounded pull of eight controls;
- monotonic session sequence, exact retransmission and acknowledgement;
- end-to-end binding of control ID, route, session, sequence, job ID and time
  window through AES-GCM associated data.

The inner cancellation remains a normal signed device envelope containing the
existing fixed `cancel_request`. The edge must decrypt it, verify the device
message and require the inner job ID to equal the outer job ID before calling
the existing cancellation gateway. The relay cannot cancel a job.

Add a sanitized `tomato-link-status` v1 operator view. `LINK: SECURE` requires
all of the following at the same observation time: connected transport,
current governed session, current non-revoked credential and ready
cancellation lane. Any connected state missing one of those controls is
`LINK: DEGRADED`; the contract rejects inconsistent secure indicators.

## Authorization and risk

Session establishment and maintenance are R0/R1 transport behavior. A
connection or lease creates no role, profile, grant, operation scope,
capability or confirmation.

Physical cancellation only stops an already authorized running job. It cannot
start work, select a tool, change parameters or dispatch arbitrary actions.
The lane therefore remains a bounded safety control rather than a new R2
execution path.

## Provisioning boundary

`InMemoryLinkCredentialVault.provision` is a fake representing a successfully
completed local provisioning ceremony. It is not that ceremony.

Physical provisioning still requires:

1. a local-only transport;
2. explicit operator intent on both displays;
3. comparison of an exact high-entropy fingerprint;
4. atomic installation or rollback on both endpoints;
5. recovery without weakening normal trust;
6. secure at-rest storage and zeroization;
7. auditable rotation and revocation.

No eFuse, flash encryption, NVS credential or USB provisioning write is
authorized by this decision.

## Required negative controls

- reused or short root secret;
- unknown, retired, stale or revoked key;
- changed authenticated lease field;
- invalid salt, TTL, clock or lease ID reuse;
- expired session;
- arbitrary priority control type;
- edge-to-device control publication;
- forged source or cross-organization destination;
- stale, oversized or replayed control;
- outer/inner job mismatch;
- ordinary queue exhaustion while cancellation remains available;
- revoked session before decrypting or dispatching cancellation.
- open WebSocket without current encryption or cancellation readiness;
- inconsistent operator-visible secure claims.

## Remaining production blockers

- physical provisioning and secure-at-rest Cardputer storage;
- production asymmetric device identity or mutually authenticated standard
  handshake;
- persistent replay, lease and idempotency state;
- public relay authentication, rate limits and global overload protection;
- cancellation wake-up scheduling and latency measurements on real hardware;
- interoperability vectors on the original ESP32-S3;
- power-loss and credential-recovery tests.

## Consequences

The simulated system now proves a complete safety path from a signed physical
cancel request, through an independently available encrypted relay lane, to
the exact running job. It also proves that rotation, revocation and expiry
invalidate managed sessions.

The tradeoff is explicit: the code now models the lifecycle a production
credential provider must enforce, but still stores secrets only in an
in-memory fake. Remote physical deployment remains blocked.

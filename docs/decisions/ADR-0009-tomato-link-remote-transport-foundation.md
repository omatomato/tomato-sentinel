# ADR-0009: Tomato Link remote transport foundation

- Status: Proposed
- Date: 2026-07-29

## Context

The original Cardputer must eventually act as a remote interface while heavy
speech, language-model and vision processing remains on an authorized PC edge
node. The Cardputer may obtain internet access through a phone hotspot or an
ordinary Wi-Fi network while the PC is on a different network behind NAT or
CGNAT.

A direct inbound PC listener would require router configuration, expose a new
public attack surface and often fail behind CGNAT. A relay reached through
outbound connections from both endpoints avoids those requirements, but the
relay becomes an untrusted routing and availability boundary.

The repository has not approved a production WebSocket stack, an end-to-end
authenticated-encryption construction, a public hosting provider, persistent
replay storage or a production credential provider. Introducing any of those
incidentally would violate the upstream intake and security baseline.

## Decision

Create a provider-neutral Tomato Link foundation with:

- a strict `tomato-link-frame` v1 contract;
- organization-, endpoint- and role-bound authenticated peers;
- device-to-edge and edge-to-device routing only;
- opaque payload handling with a 32 KiB decoded limit;
- payload length and SHA-256 integrity checks;
- a maximum frame lifetime of 120 seconds;
- monotonic per-source, per-session sequences;
- idempotent exact retransmission and rejection of changed frame IDs;
- per-destination limits of 64 frames and 256 KiB;
- bounded pulls and explicit destination acknowledgements;
- an edge outbound-client lifecycle with finite retries, bounded backoff,
  heartbeat timeout and terminal stop;
- no network listener or external destination in this change.

The current implementation is simulation-only. Its opaque payload is base64
encoded and **not encrypted**. It must not be deployed on an untrusted network
or described as confidential. Queue acknowledgement means only that the relay
accepted or removed a frame; it never means the enclosed request was
authorized, executed or completed.

The relay does not validate or dispatch inner commands. After transport
delivery, the existing authenticated device protocol validates an inner
envelope and the deterministic policy boundary evaluates the actor,
organization, device posture, profile, grants or scope, capabilities, tool,
targets, parameters, environment and confirmation.

## Authorization and risk

Opening and maintaining a bounded authenticated link is R0/R1 transport
behavior. It does not create a resource grant, operation scope, capability,
role, profile or confirmation. The risk class of an inner request remains the
risk class of its registered tool.

R2 confirmation remains exact, short-lived and plan-bound. R3 functionality
cannot be transported into executability because it remains absent from the
tool registry and action maps.

## Production blockers

Before any public relay or physical Wi-Fi firmware candidate:

1. select and register exact WebSocket/TLS and cryptographic dependencies;
2. accept a follow-up ADR for mutual endpoint authentication and end-to-end
   authenticated encryption;
3. define provisioning, rotation, revocation and recovery for physical device
   keys;
4. persist replay and idempotency state across relay restarts;
5. define an authenticated cancellation/control lane that cannot be starved by
   ordinary traffic;
6. approve explicit relay destinations, DNS/rebinding controls, timeouts,
   proxy behavior and hosting;
7. add rate limiting, abuse controls, tamper-evident audit and operational
   monitoring;
8. complete a physical Cardputer Wi-Fi power, recovery and disconnect review.

## Consequences

The edge and relay domain behavior can be tested now without cloud access,
hardware writes or an accidental public listener. A future network adapter can
depend on this bounded core rather than embedding authorization in socket
callbacks.

The tradeoff is intentional: this ADR does not yet deliver remote connectivity.
It creates the security boundary required before choosing a concrete network
and cryptographic stack.

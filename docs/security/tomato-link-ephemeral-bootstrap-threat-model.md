# Tomato Link ephemeral bootstrap threat model

## Scope

This model covers the simulation-only exchange of ephemeral public keys,
physical comparison of a short authentication string and one-shot installation
of an in-memory Tomato Link root into two fake credential providers.

It does not cover a USB listener, persistent credential storage, firmware
trust, production device identity or a remote pairing workflow.

## Assets

- X25519 ephemeral private keys;
- the derived 256-bit Tomato Link root;
- exact route and organization binding;
- operator intent expressed on both physical displays;
- integrity and freshness of the pairing transcript.

Private keys and the root are credentials. Public keys, transcript fingerprints
and sanitized lifecycle status are non-secret but integrity-sensitive.

## Trust boundaries

The device and edge create independent key pairs. Every received hello is
untrusted and validated before it changes local pairing state. The physical
operator comparison authenticates the complete role-ordered transcript; the
transport carrying public hellos is not trusted to authenticate either peer.

Each endpoint installs its independently derived root into its own fake vault.
The root never traverses the hello or status contracts.

## Controls

- strict Draft 2020-12 contracts with unknown fields rejected;
- exact role, route, organization and ceremony matching;
- public-key length and base64 validation;
- reflected-key rejection;
- exact-retry idempotency and changed-retry denial;
- finite 30-to-120-second windows;
- versioned canonical transcript and HKDF context;
- constant-time fingerprint comparison;
- `physical_display` as the only confirmation source;
- one-shot root consumption;
- terminal cancellation, expiry and reboot states;
- secret-redacted models and representations.

## Abuse cases

### Machine-in-the-middle

Changing either public key changes the displayed fingerprint. The ceremony
must fail unless the operator sees and confirms the exact same complete
fingerprint on both displays. Truncating or comparing only part of it is not
allowed.

### Replay and reflection

The transcript binds fresh ephemeral keys, roles, boot IDs, route, ceremony and
time window. A local public key reflected as the peer key is rejected. An exact
hello retry is idempotent; a changed retry terminates normal progress.

### Remote approval

An API, relay or AI response cannot confirm the ceremony. Both endpoints
require a local `physical_display` confirmation. AI cannot propose or perform
the future R2 credential installation.

### Root disclosure

Contracts and sanitized status reject secret fields. The root is delivered
only to a local sink and is removed from participant state after successful
consumption. Python may leave immutable copies in managed process memory, so
this simulation is not evidence of production zeroization.

### Partial installation

The two fake sinks are independent and cannot prove cross-device atomicity.
Production integration must either complete both installations or roll both
back. A sink that reports failure after changing state violates its required
atomic contract.

### Weak randomness

Deterministic fixture keys are never production keys. Firmware must verify the
ESP32-S3 entropy preconditions at the point of key generation. Bootloader
seeding alone is not assumed to provide an unlimited true-random stream after
application startup.

## Residual risks

- operator comparison errors or a compromised display/input path;
- compromised device or edge process memory;
- Python memory copies that cannot be guaranteed zeroized;
- denial of service by blocking or corrupting public hellos;
- clock disagreement during the short ceremony;
- no durable audit, recovery or revocation store;
- no hardware measurement of entropy or interoperability yet.

These risks block production provisioning but do not invalidate the bounded
simulation or its deterministic interoperability vector.

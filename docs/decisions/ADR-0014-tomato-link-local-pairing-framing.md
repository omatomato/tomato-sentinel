# ADR-0014: Tomato Link bounded local pairing framing

- Status: Proposed
- Date: 2026-07-29

## Context

ADR-0012 requires an exact local-only transport framing and payload cap before
physical provisioning can be designed. ADR-0013 verifies the pinned
Curve25519/HKDF firmware configuration but deliberately adds no listener,
transport or credential installation.

The first exchange contains only public, integrity-sensitive pairing hello
contracts. The transport carrying them is not trusted to authenticate either
endpoint. Authentication comes later from comparing the complete
role-ordered transcript fingerprint on both physical displays.

An unbounded stream parser, permissive version negotiation or ambiguous frame
length would create unnecessary memory, downgrade and parser-confusion risks
on the Cardputer.

## Decision

Define Tomato Link Local Pairing Frame v1 as a fixed 20-byte big-endian header
followed by at most 1,024 payload bytes:

| Offset | Bytes | Field | Required value |
| ---: | ---: | --- | --- |
| 0 | 4 | magic | ASCII `TSLP` |
| 4 | 1 | version | `1` |
| 5 | 1 | type | `1` hello, `2` cancel |
| 6 | 2 | flags | `0` |
| 8 | 4 | sequence | non-zero |
| 12 | 2 | payload length | `0..1024` |
| 14 | 2 | reserved | `0` |
| 16 | 4 | CRC-32 | header bytes `0..15`, then payload |

The CRC uses CRC-32/ISO-HDLC parameters and detects accidental corruption. It
is not a MAC, signature, identity assertion, enrollment proof or policy
decision.

A hello must carry a non-empty payload. A cancel frame must carry exactly zero
payload bytes so physical cancellation cannot dispatch arbitrary content.
Unsupported types, versions, flags and reserved bits are rejected rather than
negotiated.

Python receives immutable bytes and exposes a frozen transport model. The C++
codec uses no dynamic allocation and returns a view into caller-owned or
decoder-owned bounded memory. Its single-frame incremental decoder:

- buffers at most 1,044 bytes;
- accepts arbitrary fragmentation;
- latches terminal on invalid input, overflow or cancellation;
- rejects trailing bytes and second frames;
- clears its internal buffer when rejected, cancelled or destroyed.

The codec validates framing only. A caller must separately validate the hello
against the strict JSON Schema and then apply route, role, ceremony, boot,
time-window, reflection and idempotency controls from ADR-0012. Parsing a
frame does not enroll a device, authenticate a peer, mutate replay state or
authorize an operation.

The public language-neutral vector
`tests/interop/fixtures/tomato-link-local-frame-v1.json` is checked by Python
and C++. The existing non-deployable pairing interoperability image runs both
the crypto and framing self-tests, but still initializes no listener, network,
storage or credential path.

## Authorization and risk

Encoding and parsing public pairing metadata is R0 foundation behavior. No
role, profile, resource grant, operation scope, capability or confirmation is
required because the result grants nothing and changes no trusted state.

Future use of a cancel frame may terminate a live local ceremony but cannot
install a credential. Future credential installation remains R2 and requires
an exact short-lived physical confirmation.

## Data and trust boundaries

The payload may contain public pairing keys, endpoint identifiers, boot IDs
and timestamps. These values are non-secret but integrity-sensitive and remain
untrusted until the complete domain validation and physical fingerprint
comparison succeed.

Private keys, shared secrets, derived roots, access tokens and credential
material are forbidden from this frame.

## Required negative controls

- incomplete or incorrect magic;
- unsupported version or type;
- non-zero flags or reserved bits;
- zero sequence;
- declared payload above 1,024 bytes;
- truncated or trailing bytes;
- invalid CRC;
- empty hello;
- cancel with payload;
- incremental buffer overflow;
- data after completion;
- data after cancellation or rejection;
- public frame accepted as authentication, enrollment or authorization.

## Physical implementation boundary

This decision adds no USB or serial listener, Wi-Fi endpoint, frame dispatcher,
production entropy source, confirmation input, NVS entry, flash write, eFuse
change or credential provider. The original Cardputer is not accessed.

The next physical-design gate must specify explicit bilateral operator intent,
the full fingerprint UI and input semantics, measured entropy preconditions
and cancellation precedence. Persistent installation remains blocked on a
separate storage, rollback, rotation, revocation and recovery design.

## Consequences

The repository now has matching bounded Python and ESP32-S3 framing
implementations and can prove exact wire bytes without attaching hardware.
This reduces parser ambiguity but does not make the unauthenticated local
transport trustworthy.

The interoperability self-test still has only compile evidence on ESP32-S3.
Running it on the original Cardputer requires a separately approved,
non-provisioning hardware candidate and exact R2 flash confirmation.

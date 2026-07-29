# Tomato Sentinel contracts

Language-neutral, versioned contracts shared by firmware, edge, backend and
clients.

The current set covers commands, policy requests and decisions, tool manifests,
audit events, job transitions, temporally confirmed person events and
notification deliveries. Device protocol contracts additionally cover board
profiles, signed-envelope payloads, capability reports, visible profile state,
physical cancellation, bounded voice messages and non-secret simulated device
identity status. Speech provider output uses a normalized transcription
contract that contains text and an audio digest, never raw audio.

Passive-discovery candidates have a separate untrusted contract. They are
always labelled as simulated candidates and contain no enrollment grant,
credential, raw network address or trusted asset identity.

Tomato Link frames define bounded, short-lived opaque routing containers for
the proposed remote Cardputer path. The v1 frame is simulation-only: base64 is
not encryption, and relay acceptance is not authorization or execution.
Ephemeral pairing contracts carry only public ceremony metadata and sanitized
status; private keys and derived Tomato Link roots never cross those contracts.

The initial schemas use JSON Schema Draft 2020-12. Schema IDs resolve within
the `https://schemas.tomato-sentinel.invalid/` documentation namespace; the
reserved `.invalid` suffix prevents accidental production network resolution.

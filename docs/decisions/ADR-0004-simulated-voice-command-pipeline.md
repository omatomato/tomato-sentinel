# ADR-0004: Connect simulated voice to structured monitoring

- Status: Accepted
- Date: 2026-07-25

## Context

The bounded Cardputer push-to-talk simulator produces an authenticated voice
message, while the monitoring MVP accepts only a validated structured command.
The first end-to-end voice path must connect these boundaries without implying
that speech recognition, language-model interpretation or real audio transport
has been implemented.

Audio is personal data. Unknown audio should not be retained, logged or sent to
an unconfigured destination.

## Decision

Use an injected speech-to-text adapter behind a versioned transcription
contract. The initial adapter recognizes only reviewed audio SHA-256 fixtures,
returns a fixed Portuguese transcript and performs no inference or network
access.

Provider output is untrusted. The orchestrator validates its schema, size and
binding to the exact audio digest before using the transcript.

The initial intent extractor maps only exact reviewed transcripts to bounded
`camera.monitor` proposals. It cannot produce arbitrary actions, fields or
tool names.

The proposed target is an organization-local alias such as `garagem`, not an
internal device identifier. A deterministic alias resolver selects a
configured canonical camera ID. The existing command validator, owned-resource
resolver and policy engine still decide whether monitoring may start.

The signed voice message must report the visible `sentinel` profile. This
profile claim is an input, not authorization; actor role, trusted device,
resource grant, target ownership and tool policy remain server-side checks.

## Consequences

- The simulated MVP now exercises voice message through monitoring,
  notification and audit without external providers.
- Unknown audio, transcripts and aliases fail closed before worker creation.
- Replayed device messages cannot create duplicate workers.
- Raw audio and transcript text are absent from monitoring outcomes and audit
  events.
- Real microphone capture, Opus encoding, encrypted network transport, speech
  service deployment and model-based structured intent remain future work.

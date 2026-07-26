# Device protocol

This package implements the protocol-v1 Cardputer simulator described in
ADR-0003. It provides:

- validated original and Adv board profiles;
- the original Cardputer as the primary MVP hardware target;
- trusted capability-report derivation;
- canonical per-device HMAC envelopes for simulation;
- freshness, size, signature, sequence and bounded 1,024-ID replay checks;
- visible operating-profile state with expiring laboratory mode;
- a closed simulated command menu for registered camera, stored-inventory and
  passive-discovery actions with preloaded non-authoritative target IDs;
- bounded, visible push-to-talk capture with mandatory post-processing deletion;
- signed physical cancellation requests.

It performs no network I/O and contains no production credential-storage,
authenticated-encryption, secure-boot or firmware-signing implementation.
The command menu does not interpret free-form text, enroll cameras or grant
access; backend target resolution and policy remain authoritative.
The audio fixture accepts bytes labeled with Opus metadata but does not encode
or validate an Opus bitstream, access a microphone, transmit data or transcribe
speech.

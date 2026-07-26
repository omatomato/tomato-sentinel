# Device protocol

This package implements the protocol-v1 Cardputer simulator described in
ADR-0003. It provides:

- validated original and Adv board profiles;
- trusted capability-report derivation;
- canonical per-device HMAC envelopes for simulation;
- freshness, size, signature, sequence and bounded 1,024-ID replay checks;
- visible operating-profile state with expiring laboratory mode;
- signed physical cancellation requests.

It performs no network I/O and contains no production credential-storage,
authenticated-encryption, secure-boot or firmware-signing implementation.

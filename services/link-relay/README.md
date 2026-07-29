# Tomato Link relay core

This service implements the provider-neutral, in-memory routing boundary for
Tomato Link. It opens no socket and accepts no public traffic.

Authenticated peers are bound to one organization, endpoint ID and role.
Frames have strict schemas, short expiry, monotonic per-session sequences,
bounded payloads and bounded destination queues. The relay reports queue and
acknowledgement state only; an opaque frame is never treated as an authorized
or executed command.

Plain simulation payloads are base64 encoded but **not encrypted**. The
optional sealed-payload codec encrypts inner content with AES-256-GCM and
authenticates its outer routing binding. It accepts only caller-provided
session keys; physical key provisioning is not implemented. Public deployment
still requires an accepted ADR, persistent replay state, rate limits and a
production credential provider.

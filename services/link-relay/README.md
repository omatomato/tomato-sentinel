# Tomato Link relay core

This service currently implements only the provider-neutral, in-memory routing
boundary for Tomato Link. It opens no socket, accepts no public traffic and
provides no transport confidentiality.

Authenticated peers are bound to one organization, endpoint ID and role.
Frames have strict schemas, short expiry, monotonic per-session sequences,
bounded payloads and bounded destination queues. The relay reports queue and
acknowledgement state only; an opaque frame is never treated as an authorized
or executed command.

The simulation payload is base64 encoded but **not encrypted**. It must not be
deployed across an untrusted network. A production WebSocket adapter and
end-to-end authenticated encryption require an accepted ADR, reviewed upstream
dependencies, persistent replay state and a production credential provider.

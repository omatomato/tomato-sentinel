# Tomato Sentinel contracts

Language-neutral, versioned contracts shared by firmware, edge, backend and
clients.

The current set covers commands, policy requests and decisions, tool manifests,
audit events, job transitions, temporally confirmed person events and
notification deliveries.

The initial schemas use JSON Schema Draft 2020-12. Schema IDs resolve within
the `https://schemas.tomato-sentinel.invalid/` documentation namespace; the
reserved `.invalid` suffix prevents accidental production network resolution.

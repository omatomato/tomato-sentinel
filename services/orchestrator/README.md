# Orchestrator

The initial orchestrator slice implements the registered `camera.status` R0
query against an in-memory fake camera repository.

It validates the bounded command envelope and action parameters, rejects stale
or future requests, resolves only cameras owned by the authenticated
organization, evaluates the shared policy engine, returns a sanitized status
result and appends one idempotent audit event.

No camera connection, credential lookup, provider call, worker or external
network access occurs in this slice. Its successful audit result is therefore
`simulated`.

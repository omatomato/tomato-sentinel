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

The R1 `camera.monitor` slice adds an incremental simulated worker with:

- explicit `created -> validated -> authorized -> running` transitions;
- terminal `completed`, `cancelled` or `failed` transitions;
- at most 300 metadata-only fake frames;
- three-frame temporal confirmation for `person.detected`;
- at most one event per job;
- idempotent fake push and simulated Cardputer inbox delivery;
- cooperative cancellation and terminal audit.

The job may reach the `completed` state, but its audit result remains
`simulated` because no real camera or detector ran.

The simulated voice gateway adds:

- authenticated bounded voice-message verification;
- a reviewed audio-digest transcription fixture;
- normalized transcription validation;
- exact transcript-to-intent mapping;
- organization-local camera alias resolution;
- reuse of the existing command, policy and monitoring boundaries.

It performs no speech inference or network I/O. Unknown audio, transcripts,
aliases, profiles and device contexts fail closed before worker creation.

The simulated text-command gateway verifies the signed device envelope, binds
its source device, timestamp and correlation ID to the structured command, and
dispatches only the fixed `camera.status`, `camera.monitor` and `asset.list`
actions plus the scoped `network.passive_discovery` simulation. All paths reuse
their existing schema validation, policy, target resolution, idempotency and
audit behavior. The gateway opens no transport and does not consume the
physical Cardputer's local draft.

The R0 `asset.list` slice queries only an in-memory stored inventory. It can
filter to new and changed assets and returns bounded summaries without private
addresses or credential references. It performs no discovery, enrollment,
network I/O or long-running work.

The R1 passive-discovery slice consumes only reviewed in-memory candidates. It
requires an exact tool/network operation scope that covers the complete
duration, a configured interface, at most 120 seconds and at most 128
candidates. It records job transitions and supports cooperative or signed
physical cancellation. Candidates contain no raw address or credential and
cannot enroll themselves.

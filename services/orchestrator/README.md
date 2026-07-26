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

# First MVP

## Objective

Prove the complete command, policy, job, event and notification path before
depending on physical hardware or production providers.

## Current progress

The synchronous R0 `camera.status` precursor and the simulated R1
`camera.monitor` vertical slice are implemented.

The R1 slice includes structured validation, owned-resource resolution,
deterministic policy, a recorded job state machine, bounded metadata-only fake
frames, three-frame temporal person confirmation, normalized events,
idempotent fake push and Cardputer inbox delivery, replay protection,
cooperative cancellation and terminal audit.

All execution is marked `simulated`. No frame image, snapshot, biometric
identifier, credential or private stream URL is retained or emitted.

## Simulated vertical slice

```text
typed command fixture
    -> structured intent
    -> schema validation
    -> target resolution
    -> camera resource authorization
    -> policy decision
    -> monitoring job state machine
    -> fake recorded frame sequence
    -> temporal person confirmation
    -> normalized event
    -> idempotent fake notification
    -> simulated Cardputer inbox
```

The initial slice uses text input, a fake camera adapter and a fake
notification provider. Push-to-talk is connected only after this path is
deterministic and tested.

## Acceptance test

1. The operator requests: “Monitore a câmera da garagem por dois minutos.”
2. Intent extraction produces a versioned, validated command.
3. The target resolver selects an existing authorized camera; it cannot invent
   an identifier.
4. Policy evaluates tenant, actor, device, `sentinel` profile, resource grant,
   tool, target and parameters.
5. The job moves through valid recorded state transitions.
6. A fake frame sequence contains a person across the configured minimum
   number of frames.
7. Temporal confirmation creates one normalized event.
8. One fake notification and one simulated inbox entry are created.
9. Replaying the event creates neither a duplicate notification nor a duplicate
   inbox entry.
10. An unauthorized or cross-tenant camera produces a denial and starts no
    worker.
11. An unknown action, target or parameter is rejected before authorization.
12. Cancelling a running job stops processing and records `cancelled`.

## Required tests

- valid authorized request;
- unauthorized target;
- cross-tenant target;
- unknown action and unknown field;
- expired or disabled resource grant;
- invalid duration and oversized command;
- duplicate request and duplicate event;
- invalid state transition;
- cancellation;
- detector result below temporal threshold;
- redaction of camera credentials and private stream URLs.

## Exit criteria

The MVP is complete only when:

- schemas are versioned;
- policy is deny-by-default;
- timeouts and resource limits are enforced;
- state transitions and side effects are idempotent;
- logs and test output contain no secrets;
- the exact commands and fixtures used are reproducible;
- no real camera, external AI provider or notification provider is required for
  ordinary tests.

Facial recognition, active network probing, RF transmission, NFC writing and
USB HID are outside the first MVP.

## Verified implementation limits

- one camera per monitoring job;
- duration from 1 to 300 seconds;
- at most 300 fake frames and one normalized event per job;
- person confidence threshold `0.8` across three consecutive frames;
- five-minute command freshness window and 30-second future-clock tolerance;
- no outbound network destinations;
- cancellation is cooperative between frame-processing steps;
- ordinary tests use no hardware, camera, model or provider.

# First MVP

## Objective

Prove the complete command, policy, job, event and notification path before
depending on physical hardware or production providers.

## Current progress

The synchronous R0 `camera.status` precursor is implemented with structured
validation, owned-resource resolution, deterministic policy, sanitized fake
camera state, replay protection and idempotent audit.

This precursor does not satisfy the monitoring MVP below. It intentionally has
no worker, frame processing, notification or cancellation because it reads
existing fake state and finishes within one request. The next slice extends the
same boundaries with the R1 `camera.monitor` state machine.

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

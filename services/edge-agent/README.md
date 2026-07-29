# Tomato Sentinel edge agent

This package defines the local application boundary for capability reporting
and structured experiment proposals.

It deliberately has no HTTP server, socket listener, shell method, arbitrary
prompt endpoint or execution endpoint. A future transport adapter must provide
an authenticated device identity and organization before invoking the
application. That adapter requires an ADR covering authenticated encryption,
replay protection, payload limits, loopback/LAN exposure and certificate
rotation.

Current methods are closed and versioned:

- `edge.health`;
- `edge.capabilities`;
- `experiment.propose`, accepting only a reviewed `prompt_id`.

The simulated Cardputer may reach the first two paths and the reviewed proposal
path through `DeviceLabDashboardGateway`. It accepts only a signed
`lab_dashboard_request` whose profile, source device, timestamp and correlation
identifier match the verified envelope. This is an in-process simulation
adapter, not a network server or production authentication protocol.

`DeviceLabConfirmationGateway` separately accepts a signed
`lab_plan_confirmation` and turns it into a 60-second physical policy
confirmation only when the provisioned device is bound to the claimed operator
and organization. It does not start an experiment; the experiment engine still
checks the exact plan hash, scope, edge report and policy.

All current results identify themselves as `simulation`.
# Edge agent

The edge agent owns bounded operations that require local network or hardware
proximity. Its application boundary validates authenticated peers and exposes
only a closed method registry; it does not dynamically execute caller-supplied
names.

`OutboundTomatoLinkClient` now models the future remote connection lifecycle.
It has finite retries, bounded exponential backoff, a heartbeat timeout and a
terminal stopped state. It is transport-independent and opens no socket.

The current Tomato Link path is simulation-only. A production network adapter,
public relay destination, TLS identity and end-to-end authenticated encryption
remain blocked by ADR-0009 and its threat model.

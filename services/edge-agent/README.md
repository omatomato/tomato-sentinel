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

# Orchestrator guidance

This subtree composes validated contracts, deterministic policy decisions and
explicit adapters.

- Validate transport input before constructing domain values.
- Resolve only registered resources owned by the authenticated organization.
- Dispatch through an explicit action map; never execute names dynamically.
- Keep provider, database, network and hardware access behind injected
  protocols.
- Make command handling and audit side effects idempotent.
- Return sanitized result models rather than persistence records.
- Record simulated work as `simulated`, never `completed`.
- Instantaneous R0 queries do not create long-running jobs or cancellation
  handles.

# ADR-0006: Add a read-only stored asset inventory slice

- Status: Accepted
- Date: 2026-07-26

## Context

The product roadmap places asset visibility after the simulated monitoring
slice. The original specification distinguishes querying stored inventory,
which is R0, from passive or active discovery, which requires bounded R1
execution and an explicit network scope.

Inventory contains sensitive operational identifiers. The first increment must
prove tenant isolation, authorization and redaction without performing network
discovery or treating an observation as enrollment.

## Decision

Register `asset.list` version 1 as an R0 backend tool. It reads one canonical
registered inventory collection and returns at most 128 sanitized stored asset
summaries. It requires:

- the visible `inventory` device profile;
- the `inventory_viewer` role;
- the verified `asset_inventory_query` capability;
- a valid resource grant containing the exact inventory ID;
- a trusted device and matching actor, organization and source-device context.

The only parameter is `changes_only`. When true, the fake repository returns
assets marked `new` or `changed`; when false, it may also return `known`
assets. Results contain a canonical asset ID, display name, bounded type,
change state and observation timestamps.

Private addresses and credential references remain repository-only fields.
They are absent from result models, contracts and audit material. Results are
sorted and bounded before leaving the adapter.

The in-memory adapter represents already registered inventory. It performs no
ARP, Wi-Fi, BLE, multicast, port, ONVIF or Internet query. Unknown or
cross-organization inventory IDs return the same inaccessible-target denial
without revealing existence. Empty registered inventories return an empty
authorized result.

The operation is instantaneous and idempotent by actor, organization and
command ID. Cancellation is not applicable. Every allowed or denied execution
creates one terminal audit event, while identical command replay returns the
original outcome without another audit side effect.

The simulated Cardputer menu may compose `asset.list` only from a preloaded
non-secret inventory list. The signed text gateway dispatches it through a
fixed branch. Neither the menu entry nor the device claim grants access;
server-side policy and repository ownership remain authoritative.

## Consequences

- Stored inventory visibility can be tested without network or hardware.
- Discovery, normalization from live observations and change computation are
  not implemented by this decision.
- Any future discovery tool is a separate R1 feature requiring operation
  scope, canonical CIDR/interface targets, duration, rate limits, cancellation,
  audit and a dedicated threat model.
- Stable raw MAC addresses should not be introduced when a rotatable or keyed
  pseudonym can satisfy reconciliation.

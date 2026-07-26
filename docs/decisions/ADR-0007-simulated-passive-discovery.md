# ADR-0007: Add bounded simulated passive discovery

- Status: Accepted
- Date: 2026-07-26

## Context

Stored inventory visibility does not prove the authorization, lifecycle or
privacy boundaries required for discovery. The original specification defines
discovery as observation of candidates, not authentication, enrollment, trust
or authorization.

Even passive discovery is R1 because it observes a bounded environment over
time. A real implementation would cross the edge-to-network boundary and must
not be introduced incidentally while proving orchestration behavior.

## Decision

Register `network.passive_discovery` version 1 as an R1 edge tool operating
only in simulation. It requires:

- the visible `inventory` profile;
- the `inventory_operator` role;
- the verified `passive_network_observation` capability;
- a trusted device and matching actor, organization and source device;
- an unexpired operation scope containing the exact tool and canonical
  `network:*` target.

The scope must remain valid through the requested job duration. One job targets
one preconfigured network and one preconfigured `interface:*` identifier for 1
through 120 seconds. It returns at most 128 candidates and supports cooperative
and physical cancellation.

The adapter is an in-memory fixture and opens no socket. It validates all
candidate IDs, observer IDs, network and interface binding, timestamps,
protocols, probable types, confidence and duplicate identifiers at runtime.
The allowed simulated observation sources are existing ARP-cache or DHCP state
and already received mDNS, SSDP or WS-Discovery announcements. Active probes
are not represented.

Candidate output contains a pseudonymous `candidate:*` identifier,
classification metadata, observation timestamps and confidence. It contains
no raw MAC, IP address, credential, endpoint, asset ID or organization ID.
Every result is fixed to `enrollment_status: candidate` and
`execution_mode: simulated`.

The job records explicit created, validated, authorized, running and terminal
transitions. Command replay is idempotent, candidate count and duration are
bounded, cancellation is context-bound, and allowed, denied, failed or
cancelled terminal states are audited with the operation scope ID.

The simulated Cardputer menu may compose this action only for a preloaded
network/interface pair. The authenticated text gateway dispatches it through a
fixed branch. Neither device-side presentation state nor discovery output
creates an asset, credential, resource grant or trust state.

## Consequences

- Scope, lifecycle, cancellation and candidate boundaries can be tested
  without network access.
- The current implementation does not read an ARP table, DHCP lease, multicast
  packet, interface, CIDR or radio.
- Enrollment remains a separate operator-approved workflow with separate
  credentials.
- A real edge adapter requires a new threat model, exact destination and
  interface controls, rate and buffer limits, cancellation validation,
  privacy review and hardware or network acceptance evidence.

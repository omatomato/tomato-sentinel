# Authorization model

## Principles

- deny by default;
- canonical comparison, never substring authorization;
- tenant and ownership checks precede target use;
- authorization is evaluated at execution time, not only at planning time;
- confirmation cannot grant an otherwise unauthorized operation;
- the LLM cannot modify policy inputs or override a decision.

## Distinct concepts

### Role

An operator role controls administrative and business permissions. Examples
may include `viewer`, `operator`, `security_operator` and `organization_admin`.
Roles are not device operating profiles.

### Profile

A profile is the visible operating mode of a Cardputer or operator session:
`assistant`, `sentinel`, `inventory`, `lab` or `recovery`.

### Resource grant

A resource grant authorizes ordinary access to registered resources such as a
camera, sensor or saved asset group. Sentinel camera monitoring uses a resource
grant rather than inventing a cybersecurity scope.

### Operation scope

An operation scope is a time-bounded authorization for inventory or laboratory
operations. It declares canonical target sets and allowed tool IDs.

### Capability

A capability is functionality verified by trusted firmware, edge
configuration or an approved service adapter. A client claim alone cannot add
a capability.

### Confirmation

A confirmation approves one immutable plan hash, actor, device, target set and
short expiry. It cannot be replayed for changed parameters.

## Policy request

```json
{
  "actor": {
    "actor_id": "user-01",
    "organization_id": "org-01",
    "roles": ["operator"]
  },
  "device": {
    "device_id": "cardputer-01",
    "trust_state": "trusted",
    "firmware_version": "0.1.0"
  },
  "profile": "sentinel",
  "resource_grant": {
    "resource_ids": ["camera:garage-01"]
  },
  "operation_scope": null,
  "tool": {
    "tool_id": "camera.monitor",
    "version": 1,
    "risk_class": "R1"
  },
  "targets": ["camera:garage-01"],
  "parameters": {
    "duration_seconds": 120
  },
  "environment": {
    "network_id": "home-lan",
    "physical_confirmation": false
  }
}
```

## Policy decision

Use one representation for confirmation:

```json
{
  "decision": "allow_with_confirmation",
  "reason_code": "AUTHORIZED_ACTIVE_OPERATION",
  "obligations": [
    {
      "type": "physical_confirmation",
      "expires_in_seconds": 30
    },
    {
      "type": "execution_limit",
      "maximum_duration_seconds": 60,
      "maximum_requests": 100
    }
  ]
}
```

Valid decisions are:

```text
allow
allow_with_confirmation
deny
require_scope
require_profile_change
require_physical_confirmation
```

`allow` never carries a hidden confirmation requirement.

## Canonical target validation

- IP addresses and CIDRs use parsed network representations.
- Domains use normalized labels and boundary-aware suffix rules.
- Device and camera identifiers use exact typed IDs.
- Wildcards are allowed only in fields whose schema explicitly defines them.
- URLs are normalized and separately checked by outbound network policy.
- Expired grants, scopes and confirmations deny execution.

## Device trust states

```text
unprovisioned
trusted
outdated
recovery
revoked
compromised
```

Policy declares which R0 recovery operations are available in non-trusted
states. Laboratory and R2 operations require `trusted`.

## Required denial tests

- cross-tenant identifier;
- modified object identifier;
- unknown tool or version;
- missing verified capability;
- wrong profile;
- expired grant or scope;
- target outside canonical scope;
- changed plan after confirmation;
- replayed confirmation;
- revoked or outdated device where trust is required;
- unsupported parameter and limit overflow.

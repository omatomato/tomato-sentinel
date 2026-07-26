"""Immutable policy-domain values."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Profile(StrEnum):
    ASSISTANT = "assistant"
    SENTINEL = "sentinel"
    INVENTORY = "inventory"
    LAB = "lab"
    RECOVERY = "recovery"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class TrustState(StrEnum):
    UNPROVISIONED = "unprovisioned"
    TRUSTED = "trusted"
    OUTDATED = "outdated"
    RECOVERY = "recovery"
    REVOKED = "revoked"
    COMPROMISED = "compromised"


class AuthorizationKind(StrEnum):
    NONE = "none"
    RESOURCE_GRANT = "resource_grant"
    OPERATION_SCOPE = "operation_scope"


class ConfirmationMethod(StrEnum):
    OPERATOR = "operator"
    PHYSICAL = "physical"


class Decision(StrEnum):
    ALLOW = "allow"
    ALLOW_WITH_CONFIRMATION = "allow_with_confirmation"
    DENY = "deny"
    REQUIRE_SCOPE = "require_scope"
    REQUIRE_PROFILE_CHANGE = "require_profile_change"
    REQUIRE_PHYSICAL_CONFIRMATION = "require_physical_confirmation"


class ReasonCode(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    AUTHORIZED_CONFIRMATION_REQUIRED = "AUTHORIZED_CONFIRMATION_REQUIRED"
    ACTOR_ROLE_REQUIRED = "ACTOR_ROLE_REQUIRED"
    CAPABILITY_REQUIRED = "CAPABILITY_REQUIRED"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    DEVICE_NOT_TRUSTED = "DEVICE_NOT_TRUSTED"
    DURATION_INVALID = "DURATION_INVALID"
    DURATION_LIMIT_EXCEEDED = "DURATION_LIMIT_EXCEEDED"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    GRANT_REQUIRED = "GRANT_REQUIRED"
    ORGANIZATION_MISMATCH = "ORGANIZATION_MISMATCH"
    PROFILE_REQUIRED = "PROFILE_REQUIRED"
    SCOPE_EXPIRED = "SCOPE_EXPIRED"
    SCOPE_REQUIRED = "SCOPE_REQUIRED"
    TARGET_COUNT_INVALID = "TARGET_COUNT_INVALID"
    TARGET_NOT_AUTHORIZED = "TARGET_NOT_AUTHORIZED"
    TOOL_NOT_AUTHORIZED = "TOOL_NOT_AUTHORIZED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    organization_id: str
    roles: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class DeviceContext:
    device_id: str
    organization_id: str
    trust_state: TrustState
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ResourceGrant:
    organization_id: str
    resource_ids: frozenset[str]
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class OperationScope:
    scope_id: str
    organization_id: str
    tool_ids: frozenset[str]
    target_ids: frozenset[str]
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class Confirmation:
    actor_id: str
    device_id: str
    plan_hash: str
    method: ConfirmationMethod
    valid_until: datetime


@dataclass(frozen=True, slots=True)
class ToolManifest:
    tool_id: str
    version: int
    risk_class: RiskClass
    required_profile: Profile
    authorization_kind: AuthorizationKind
    required_roles: frozenset[str] = field(default_factory=frozenset)
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    requires_confirmation: bool = False
    requires_physical_confirmation: bool = False
    maximum_duration_seconds: int | None = None
    maximum_targets: int = 1


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    actor: ActorContext
    device: DeviceContext
    profile: Profile
    tool_id: str
    tool_version: int
    targets: tuple[str, ...]
    parameters: Mapping[str, object]
    evaluated_at: datetime
    plan_hash: str
    resource_grant: ResourceGrant | None = None
    operation_scope: OperationScope | None = None
    confirmation: Confirmation | None = None


@dataclass(frozen=True, slots=True)
class Obligation:
    obligation_type: str
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: Decision
    reason_code: ReasonCode
    obligations: tuple[Obligation, ...] = ()

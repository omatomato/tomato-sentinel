"""Immutable values used by the simulated orchestrator slice."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tomato_sentinel_policy import (
    ActorContext,
    DeviceContext,
    OperationScope,
    Profile,
    ResourceGrant,
)


class CameraState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ExecutionStatus(StrEnum):
    SIMULATED = "simulated"
    DENIED = "denied"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CameraRecord:
    camera_id: str
    organization_id: str
    display_name: str
    status: CameraState
    observed_at: datetime
    credential_reference: str
    private_stream_url: str


@dataclass(frozen=True, slots=True)
class CameraStatus:
    camera_id: str
    display_name: str
    status: CameraState
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    actor: ActorContext
    device: DeviceContext
    resource_grant: ResourceGrant
    operation_scope: OperationScope | None = None


@dataclass(frozen=True, slots=True)
class ValidatedCommand:
    command_id: str
    actor_id: str
    organization_id: str
    source_device_id: str
    profile: Profile
    action: str
    targets: tuple[str, ...]
    parameters: Mapping[str, object]
    requested_at: datetime
    correlation_id: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    contract_version: int
    event_id: str
    timestamp: datetime
    actor_id: str
    organization_id: str
    device_id: str
    profile: Profile
    scope_id: str | None
    tool_id: str
    tool_version: int
    targets: tuple[str, ...]
    parameters_hash: str
    plan_hash: str
    policy_decision: str
    reason_code: str
    confirmation_method: str | None
    result: ExecutionStatus
    correlation_id: str


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    contract_version: int
    command_id: str
    status: ExecutionStatus
    cameras: tuple[CameraStatus, ...]
    reason_code: str
    audit_event_id: str

"""Immutable values for registered research modules and experiment plans."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tomato_sentinel_policy import AuthorizationKind, Profile, RiskClass


class ExecutionLocation(StrEnum):
    CARDPUTER = "cardputer"
    EDGE = "edge"
    BACKEND = "backend"
    EXTERNAL_SERVICE = "external_service"


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    module_id: str
    version: int
    display_name: str
    category: str
    execution_location: ExecutionLocation
    risk_class: RiskClass
    required_profile: Profile
    authorization_kind: AuthorizationKind
    required_roles: frozenset[str]
    required_capabilities: frozenset[str]
    required_hardware: frozenset[str]
    requires_confirmation: bool
    requires_physical_confirmation: bool
    maximum_duration_seconds: int
    maximum_samples: int
    supports_cancel: bool
    executor_id: str
    parameters_schema: Mapping[str, object]
    result_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    experiment_id: str
    module_id: str
    module_version: int
    actor_id: str
    organization_id: str
    source_device_id: str
    profile: Profile
    targets: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    parameters: Mapping[str, object]
    requested_at: datetime
    correlation_id: str
    execution_mode: str
    plan_hash: str
    operation_scope_id: str

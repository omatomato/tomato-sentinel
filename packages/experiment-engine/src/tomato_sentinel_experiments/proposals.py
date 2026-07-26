"""Untrusted AI proposal validation and trusted plan binding."""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from tomato_sentinel_policy import ActorContext, DeviceContext, Profile

from .models import ExperimentPlan
from .plans import ExperimentPlanValidator, canonical_plan_hash

MAX_PROPOSAL_BYTES = 16_384


class ExperimentProposalRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class LocalExperimentModel(Protocol):
    """Provider boundary: output is data and is never executed directly."""

    def propose(self, prompt_id: str) -> Mapping[str, object]: ...


class FixtureLocalExperimentModel:
    """Reviewed deterministic stand-in for a future local model provider."""

    def __init__(self, proposals: Mapping[str, Mapping[str, object]]) -> None:
        self._proposals = {key: dict(value) for key, value in proposals.items()}

    def propose(self, prompt_id: str) -> Mapping[str, object]:
        try:
            return dict(self._proposals[prompt_id])
        except KeyError as error:
            raise ExperimentProposalRejectedError("PROMPT_NOT_REVIEWED") from error


class ExperimentProposalValidator:
    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)

    def validate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        try:
            encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ExperimentProposalRejectedError("PROPOSAL_NOT_JSON") from error
        if len(encoded.encode()) > MAX_PROPOSAL_BYTES:
            raise ExperimentProposalRejectedError("PROPOSAL_TOO_LARGE")
        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise ExperimentProposalRejectedError("PROPOSAL_SCHEMA_INVALID") from error
        return dict(payload)


class ExperimentProposalBinder:
    def __init__(
        self,
        *,
        validator: ExperimentProposalValidator,
        plan_validator: ExperimentPlanValidator,
        module_aliases: Mapping[str, tuple[str, int]],
        target_aliases: Mapping[str, str],
        fixture_aliases: Mapping[str, str],
    ) -> None:
        self._validator = validator
        self._plan_validator = plan_validator
        self._module_aliases = dict(module_aliases)
        self._target_aliases = dict(target_aliases)
        self._fixture_aliases = dict(fixture_aliases)

    def bind(
        self,
        proposal: Mapping[str, object],
        *,
        experiment_id: str,
        correlation_id: str,
        actor: ActorContext,
        source_device: DeviceContext,
        profile: Profile,
        operation_scope_id: str,
        requested_at: datetime,
    ) -> tuple[dict[str, object], ExperimentPlan]:
        validated = self._validator.validate(proposal)
        try:
            module_id, module_version = self._module_aliases[
                cast(str, validated["module_alias"])
            ]
            target = self._target_aliases[cast(str, validated["target_alias"])]
            fixtures = [
                self._fixture_aliases[alias]
                for alias in cast(list[str], validated["fixture_aliases"])
            ]
        except KeyError as error:
            raise ExperimentProposalRejectedError("PROPOSAL_ALIAS_UNKNOWN") from error
        if actor.organization_id != source_device.organization_id:
            raise ExperimentProposalRejectedError("PROPOSAL_CONTEXT_MISMATCH")
        if requested_at.tzinfo is None:
            raise ExperimentProposalRejectedError("PROPOSAL_TIMEZONE_REQUIRED")

        payload: dict[str, object] = {
            "contract_version": 1,
            "experiment_id": experiment_id,
            "module_id": module_id,
            "module_version": module_version,
            "actor_id": actor.actor_id,
            "organization_id": actor.organization_id,
            "source_device_id": source_device.device_id,
            "profile": profile.value,
            "targets": [target],
            "fixture_ids": fixtures,
            "parameters": dict(cast(Mapping[str, object], validated["parameters"])),
            "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
            "correlation_id": correlation_id,
            "execution_mode": "simulation",
            "operation_scope_id": operation_scope_id,
        }
        payload["plan_hash"] = canonical_plan_hash(payload)
        plan = self._plan_validator.validate(payload)
        return payload, plan

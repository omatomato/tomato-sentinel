"""Strict validation and canonical hashing for experiment plans."""

import json
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from tomato_sentinel_policy import Profile

from .models import ExperimentPlan
from .registry import ModuleRegistry

MAX_PLAN_BYTES = 32_768


class ExperimentPlanRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def canonical_plan_hash(payload: Mapping[str, object]) -> str:
    """Hash only immutable execution inputs, excluding the supplied hash."""
    covered = {
        key: payload[key]
        for key in (
            "contract_version",
            "experiment_id",
            "module_id",
            "module_version",
            "actor_id",
            "organization_id",
            "source_device_id",
            "profile",
            "targets",
            "fixture_ids",
            "parameters",
            "requested_at",
            "correlation_id",
            "execution_mode",
            "operation_scope_id",
        )
    }
    encoded = json.dumps(
        covered,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


class ExperimentPlanValidator:
    def __init__(
        self,
        plan_schema: Mapping[str, Any],
        module_registry: ModuleRegistry,
    ) -> None:
        Draft202012Validator.check_schema(plan_schema)
        self._validator = Draft202012Validator(
            plan_schema,
            format_checker=FormatChecker(),
        )
        self._module_registry = module_registry

    def validate(self, payload: Mapping[str, object]) -> ExperimentPlan:
        try:
            encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ExperimentPlanRejectedError("PLAN_NOT_JSON") from error
        if len(encoded.encode()) > MAX_PLAN_BYTES:
            raise ExperimentPlanRejectedError("PLAN_TOO_LARGE")

        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise ExperimentPlanRejectedError("PLAN_SCHEMA_INVALID") from error

        module_id = cast(str, payload["module_id"])
        module_version = cast(int, payload["module_version"])
        try:
            manifest = self._module_registry.get(module_id, module_version)
        except ValueError as error:
            raise ExperimentPlanRejectedError("PLAN_MODULE_NOT_REGISTERED") from error

        profile = Profile(cast(str, payload["profile"]))
        if profile is not manifest.required_profile:
            raise ExperimentPlanRejectedError("PLAN_PROFILE_MISMATCH")

        parameters = cast(Mapping[str, object], payload["parameters"])
        try:
            Draft202012Validator(manifest.parameters_schema).validate(parameters)
        except ValidationError as error:
            raise ExperimentPlanRejectedError("PLAN_PARAMETERS_INVALID") from error

        sample_count = parameters.get("sample_count")
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or sample_count > manifest.maximum_samples
        ):
            raise ExperimentPlanRejectedError("PLAN_SAMPLE_LIMIT_INVALID")
        duration = parameters.get("duration_seconds")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration > manifest.maximum_duration_seconds
        ):
            raise ExperimentPlanRejectedError("PLAN_DURATION_LIMIT_INVALID")

        expected_hash = canonical_plan_hash(payload)
        if cast(str, payload["plan_hash"]) != expected_hash:
            raise ExperimentPlanRejectedError("PLAN_HASH_MISMATCH")

        requested_at = datetime.fromisoformat(
            cast(str, payload["requested_at"]).replace("Z", "+00:00")
        )
        if requested_at.tzinfo is None:
            raise ExperimentPlanRejectedError("PLAN_TIMEZONE_REQUIRED")

        return ExperimentPlan(
            experiment_id=cast(str, payload["experiment_id"]),
            module_id=module_id,
            module_version=module_version,
            actor_id=cast(str, payload["actor_id"]),
            organization_id=cast(str, payload["organization_id"]),
            source_device_id=cast(str, payload["source_device_id"]),
            profile=profile,
            targets=tuple(cast(list[str], payload["targets"])),
            fixture_ids=tuple(cast(list[str], payload["fixture_ids"])),
            parameters=dict(parameters),
            requested_at=requested_at,
            correlation_id=cast(str, payload["correlation_id"]),
            execution_mode=cast(str, payload["execution_mode"]),
            plan_hash=expected_hash,
            operation_scope_id=cast(str, payload["operation_scope_id"]),
        )

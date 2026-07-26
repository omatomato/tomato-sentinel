"""Deny-by-default registry for versioned experiment modules."""

from collections.abc import Mapping
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from tomato_sentinel_policy import AuthorizationKind, Profile, RiskClass

from .models import ExecutionLocation, ModuleManifest


class ModuleRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ModuleRegistry:
    def __init__(self, manifest_schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(manifest_schema)
        self._validator = Draft202012Validator(manifest_schema)
        self._modules: dict[tuple[str, int], ModuleManifest] = {}
        self._executors: dict[str, tuple[str, int]] = {}

    def register(self, payload: Mapping[str, object]) -> ModuleManifest:
        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise ModuleRejectedError("MODULE_MANIFEST_INVALID") from error

        parameters_schema = cast(Mapping[str, object], payload["parameters_schema"])
        result_schema = cast(Mapping[str, object], payload["result_schema"])
        try:
            Draft202012Validator.check_schema(parameters_schema)
            Draft202012Validator.check_schema(result_schema)
        except SchemaError as error:
            raise ModuleRejectedError("MODULE_EMBEDDED_SCHEMA_INVALID") from error

        module_id = cast(str, payload["module_id"])
        version = cast(int, payload["version"])
        key = (module_id, version)
        if key in self._modules:
            raise ModuleRejectedError("MODULE_ALREADY_REGISTERED")
        executor_id = cast(str, payload["executor_id"])
        if executor_id in self._executors:
            raise ModuleRejectedError("EXECUTOR_ALREADY_BOUND")

        risk_class = RiskClass(cast(str, payload["risk_class"]))
        authorization_kind = AuthorizationKind(cast(str, payload["authorization_kind"]))
        if risk_class is RiskClass.R3:
            raise ModuleRejectedError("R3_MODULE_PROHIBITED")
        if risk_class in {RiskClass.R1, RiskClass.R2} and not cast(
            bool,
            payload["supports_cancel"],
        ):
            raise ModuleRejectedError("CANCELLATION_REQUIRED")
        if cast(bool, payload["requires_physical_confirmation"]) and not cast(
            bool,
            payload["requires_confirmation"],
        ):
            raise ModuleRejectedError("PHYSICAL_CONFIRMATION_REQUIRES_CONFIRMATION")
        if risk_class is RiskClass.R2 and (
            authorization_kind is not AuthorizationKind.OPERATION_SCOPE
            or not cast(bool, payload["requires_confirmation"])
        ):
            raise ModuleRejectedError("R2_CONTROLS_REQUIRED")

        manifest = ModuleManifest(
            module_id=module_id,
            version=version,
            display_name=cast(str, payload["display_name"]),
            category=cast(str, payload["category"]),
            execution_location=ExecutionLocation(
                cast(str, payload["execution_location"])
            ),
            risk_class=risk_class,
            required_profile=Profile(cast(str, payload["required_profile"])),
            authorization_kind=authorization_kind,
            required_roles=frozenset(cast(list[str], payload["required_roles"])),
            required_capabilities=frozenset(
                cast(list[str], payload["required_capabilities"])
            ),
            required_hardware=frozenset(cast(list[str], payload["required_hardware"])),
            requires_confirmation=cast(bool, payload["requires_confirmation"]),
            requires_physical_confirmation=cast(
                bool,
                payload["requires_physical_confirmation"],
            ),
            maximum_duration_seconds=cast(
                int,
                payload["maximum_duration_seconds"],
            ),
            maximum_samples=cast(int, payload["maximum_samples"]),
            supports_cancel=cast(bool, payload["supports_cancel"]),
            executor_id=executor_id,
            parameters_schema=dict(parameters_schema),
            result_schema=dict(result_schema),
        )
        self._modules[key] = manifest
        self._executors[executor_id] = key
        return manifest

    def get(self, module_id: str, version: int) -> ModuleManifest:
        try:
            return self._modules[(module_id, version)]
        except KeyError as error:
            raise ModuleRejectedError("MODULE_NOT_REGISTERED") from error

    @property
    def modules(self) -> tuple[ModuleManifest, ...]:
        return tuple(self._modules[key] for key in sorted(self._modules))

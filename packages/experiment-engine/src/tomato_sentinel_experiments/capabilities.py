"""Validation of short-lived, identity-bound edge capability reports."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .registry import ModuleRegistry

MAX_CAPABILITY_REPORT_BYTES = 32_768


class CapabilityReportRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class AvailableModule:
    module_id: str
    module_version: int
    executor_id: str


@dataclass(frozen=True, slots=True)
class ValidatedCapabilityReport:
    edge_id: str
    organization_id: str
    agent_version: str
    generated_at: datetime
    valid_until: datetime
    execution_mode: str
    modules: tuple[AvailableModule, ...]
    report_hash: str


def canonical_capability_report_hash(payload: Mapping[str, object]) -> str:
    covered = {key: value for key, value in payload.items() if key != "report_hash"}
    encoded = json.dumps(
        covered,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


class CapabilityReportValidator:
    def __init__(
        self,
        report_schema: Mapping[str, Any],
        module_registry: ModuleRegistry,
    ) -> None:
        Draft202012Validator.check_schema(report_schema)
        self._validator = Draft202012Validator(
            report_schema,
            format_checker=FormatChecker(),
        )
        self._module_registry = module_registry

    def validate(
        self,
        payload: Mapping[str, object],
        *,
        authenticated_edge_id: str,
        authenticated_organization_id: str,
        evaluated_at: datetime,
    ) -> ValidatedCapabilityReport:
        try:
            encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise CapabilityReportRejectedError("CAPABILITY_REPORT_NOT_JSON") from error
        if len(encoded.encode()) > MAX_CAPABILITY_REPORT_BYTES:
            raise CapabilityReportRejectedError("CAPABILITY_REPORT_TOO_LARGE")
        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise CapabilityReportRejectedError(
                "CAPABILITY_REPORT_SCHEMA_INVALID"
            ) from error

        edge_id = cast(str, payload["edge_id"])
        organization_id = cast(str, payload["organization_id"])
        if (
            edge_id != authenticated_edge_id
            or organization_id != authenticated_organization_id
        ):
            raise CapabilityReportRejectedError("CAPABILITY_IDENTITY_MISMATCH")
        expected_hash = canonical_capability_report_hash(payload)
        if cast(str, payload["report_hash"]) != expected_hash:
            raise CapabilityReportRejectedError("CAPABILITY_REPORT_HASH_MISMATCH")

        generated_at = _parse_time(cast(str, payload["generated_at"]))
        valid_until = _parse_time(cast(str, payload["valid_until"]))
        if generated_at > evaluated_at or valid_until <= evaluated_at:
            raise CapabilityReportRejectedError("CAPABILITY_REPORT_EXPIRED")
        if (valid_until - generated_at).total_seconds() > 300:
            raise CapabilityReportRejectedError("CAPABILITY_REPORT_TTL_EXCEEDED")

        available: list[AvailableModule] = []
        seen_modules: set[tuple[str, int]] = set()
        for raw in cast(list[Mapping[str, object]], payload["modules"]):
            module_id = cast(str, raw["module_id"])
            module_version = cast(int, raw["module_version"])
            key = (module_id, module_version)
            if key in seen_modules:
                raise CapabilityReportRejectedError("CAPABILITY_MODULE_DUPLICATED")
            seen_modules.add(key)
            try:
                manifest = self._module_registry.get(module_id, module_version)
            except ValueError as error:
                raise CapabilityReportRejectedError(
                    "CAPABILITY_MODULE_NOT_REGISTERED"
                ) from error
            executor_id = cast(str, raw["executor_id"])
            capabilities = frozenset(cast(list[str], raw["capabilities"]))
            hardware = frozenset(cast(list[str], raw["hardware"]))
            if executor_id != manifest.executor_id:
                raise CapabilityReportRejectedError("CAPABILITY_EXECUTOR_MISMATCH")
            if not manifest.required_capabilities.issubset(capabilities):
                raise CapabilityReportRejectedError("CAPABILITY_REQUIRED_MISSING")
            if not manifest.required_hardware.issubset(hardware):
                raise CapabilityReportRejectedError("CAPABILITY_HARDWARE_MISSING")
            available.append(
                AvailableModule(
                    module_id=module_id,
                    module_version=module_version,
                    executor_id=executor_id,
                )
            )
        return ValidatedCapabilityReport(
            edge_id=edge_id,
            organization_id=organization_id,
            agent_version=cast(str, payload["agent_version"]),
            generated_at=generated_at,
            valid_until=valid_until,
            execution_mode=cast(str, payload["execution_mode"]),
            modules=tuple(available),
            report_hash=expected_hash,
        )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CapabilityReportRejectedError("CAPABILITY_TIMEZONE_REQUIRED")
    return parsed

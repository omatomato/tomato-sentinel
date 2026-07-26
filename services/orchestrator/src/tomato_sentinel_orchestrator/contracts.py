"""Runtime validation at the structured-command trust boundary."""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from tomato_sentinel_policy import Profile

from .models import ValidatedCommand

MAX_COMMAND_BYTES = 16_384


class CommandRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ContractValidator:
    """Validate a command envelope and one explicitly registered action."""

    def __init__(
        self,
        command_schema: Mapping[str, Any],
        tool_manifests: tuple[Mapping[str, Any], ...],
    ) -> None:
        Draft202012Validator.check_schema(command_schema)
        self._command_validator = Draft202012Validator(
            command_schema,
            format_checker=FormatChecker(),
        )
        self._parameter_validators: dict[str, Draft202012Validator] = {}
        for manifest in tool_manifests:
            action = str(manifest["tool_id"])
            if action in self._parameter_validators:
                raise ValueError(f"duplicate action contract: {action}")
            parameters_schema = manifest["parameters_schema"]
            if not isinstance(parameters_schema, Mapping):
                raise TypeError("parameters_schema must be an object")
            Draft202012Validator.check_schema(parameters_schema)
            self._parameter_validators[action] = Draft202012Validator(parameters_schema)

    def validate(self, payload: Mapping[str, object]) -> ValidatedCommand:
        try:
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        except (TypeError, ValueError) as error:
            raise CommandRejectedError("COMMAND_NOT_JSON") from error
        if len(encoded) > MAX_COMMAND_BYTES:
            raise CommandRejectedError("COMMAND_TOO_LARGE")

        try:
            self._command_validator.validate(payload)
        except ValidationError as error:
            raise CommandRejectedError("COMMAND_SCHEMA_INVALID") from error

        action = payload["action"]
        if not isinstance(action, str):
            raise CommandRejectedError("COMMAND_SCHEMA_INVALID")
        parameter_validator = self._parameter_validators.get(action)
        if parameter_validator is None:
            raise CommandRejectedError("ACTION_NOT_REGISTERED")
        try:
            parameter_validator.validate(payload["parameters"])
        except ValidationError as error:
            raise CommandRejectedError("PARAMETERS_SCHEMA_INVALID") from error

        correlation_id = payload.get("correlation_id", payload["command_id"])
        targets = cast(list[object], payload["targets"])
        parameters = cast(Mapping[str, object], payload["parameters"])
        return ValidatedCommand(
            command_id=str(payload["command_id"]),
            actor_id=str(payload["actor_id"]),
            organization_id=str(payload["organization_id"]),
            source_device_id=str(payload["source_device_id"]),
            profile=Profile(str(payload["profile"])),
            action=action,
            targets=tuple(str(target) for target in targets),
            parameters=dict(parameters),
            requested_at=datetime.fromisoformat(
                str(payload["requested_at"]).replace("Z", "+00:00")
            ),
            correlation_id=str(correlation_id),
        )

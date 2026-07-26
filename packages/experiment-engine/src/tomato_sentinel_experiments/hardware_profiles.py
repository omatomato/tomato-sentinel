"""Registry for declarative, disabled physical module candidates."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class HardwareProfileRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class InactiveHardwareProfile:
    hardware_id: str
    version: int
    display_name: str
    compatible_board_profiles: frozenset[str]
    bus: str
    interaction_modes: frozenset[str]


class InactiveHardwareRegistry:
    """Accepts only profiles that cannot initialize or drive hardware."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)
        self._profiles: dict[tuple[str, int], InactiveHardwareProfile] = {}

    def register(self, payload: Mapping[str, object]) -> InactiveHardwareProfile:
        try:
            self._validator.validate(payload)
        except ValidationError as error:
            raise HardwareProfileRejectedError("HARDWARE_PROFILE_INVALID") from error
        key = (cast(str, payload["hardware_id"]), cast(int, payload["version"]))
        if key in self._profiles:
            raise HardwareProfileRejectedError("HARDWARE_PROFILE_DUPLICATED")
        profile = InactiveHardwareProfile(
            hardware_id=key[0],
            version=key[1],
            display_name=cast(str, payload["display_name"]),
            compatible_board_profiles=frozenset(
                cast(list[str], payload["compatible_board_profiles"])
            ),
            bus=cast(str, payload["bus"]),
            interaction_modes=frozenset(cast(list[str], payload["interaction_modes"])),
        )
        self._profiles[key] = profile
        return profile

    @property
    def profiles(self) -> tuple[InactiveHardwareProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

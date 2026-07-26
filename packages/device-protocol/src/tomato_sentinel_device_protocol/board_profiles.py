"""Validated conversion from declarative hardware profiles."""

from collections.abc import Mapping
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .models import BoardProfile


def load_board_profile(
    payload: Mapping[str, object],
    schema: Mapping[str, Any],
) -> BoardProfile:
    try:
        Draft202012Validator(schema).validate(payload)
    except ValidationError as error:
        raise ValueError("BOARD_PROFILE_INVALID") from error
    capabilities = cast(Mapping[str, bool], payload["capabilities"])
    constraints = cast(Mapping[str, object], payload["constraints"])
    return BoardProfile(
        board_profile_id=cast(str, payload["board_profile_id"]),
        hardware_revision=cast(str, payload["hardware_revision"]),
        controller=cast(str, payload["controller"]),
        capabilities=frozenset(
            name for name, available in capabilities.items() if available
        ),
        maximum_message_bytes=cast(int, constraints["maximum_message_bytes"]),
        microphone_speaker_simultaneous=cast(
            bool,
            constraints["microphone_speaker_simultaneous"],
        ),
    )

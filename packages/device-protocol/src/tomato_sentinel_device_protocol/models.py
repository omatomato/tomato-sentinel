"""Immutable simulator values for board and device protocol state."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from tomato_sentinel_policy import Profile


@dataclass(frozen=True, slots=True)
class BoardProfile:
    board_profile_id: str
    hardware_revision: str
    controller: str
    capabilities: frozenset[str]
    maximum_message_bytes: int
    microphone_speaker_simultaneous: bool


@dataclass(frozen=True, slots=True)
class ProvisionedDevice:
    device_id: str
    key_id: str
    board_profile: BoardProfile
    firmware_version: str
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedDeviceMessage:
    message_id: str
    device_id: str
    sent_at: datetime
    correlation_id: str
    sequence: int
    payload_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProfileState:
    active_profile: Profile
    indicator: str
    operator_id: str | None
    scope_id: str | None
    expires_at: datetime | None

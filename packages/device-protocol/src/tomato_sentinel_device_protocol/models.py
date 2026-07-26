"""Immutable simulator values for board and device protocol state."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tomato_sentinel_policy import Profile


class DeviceIdentityState(StrEnum):
    TRUSTED = "trusted"
    REVOKED = "revoked"


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
class DeviceIdentityStatus:
    device_id: str
    key_id: str
    board_profile_id: str
    firmware_version: str
    identity_revision: int
    state: DeviceIdentityState

    def to_contract(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "device_id": self.device_id,
            "key_id": self.key_id,
            "board_profile_id": self.board_profile_id,
            "firmware_version": self.firmware_version,
            "identity_revision": self.identity_revision,
            "state": self.state.value,
            "execution_mode": "simulation",
        }


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

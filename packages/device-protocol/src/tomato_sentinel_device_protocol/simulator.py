"""Cardputer state and message generation without physical hardware."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from tomato_sentinel_policy import Profile

from .audio import PushToTalkRecorder
from .models import BoardProfile, ProfileState
from .protocol import sign_envelope


class CardputerSimulator:
    def __init__(
        self,
        *,
        device_id: str,
        key_id: str,
        secret: bytes,
        board_profile: BoardProfile,
        firmware_version: str,
        boot_id: str,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("simulation device secret must contain at least 32 bytes")
        self.device_id = device_id
        self.key_id = key_id
        self._secret = bytes(secret)
        self.board_profile = board_profile
        self.firmware_version = firmware_version
        self.boot_id = boot_id.replace(":", "-")
        self._sequence = 0
        self._profile = ProfileState(
            active_profile=Profile.ASSISTANT,
            indicator="PROFILE: ASSISTANT",
            operator_id=None,
            scope_id=None,
            expires_at=None,
        )

    @property
    def profile_state(self) -> ProfileState:
        return self._profile

    def switch_profile(
        self,
        profile: Profile,
        *,
        changed_at: datetime,
        unlocked: bool,
        operator_id: str | None = None,
        active_scope_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> ProfileState:
        _require_aware(changed_at)
        if not unlocked:
            raise PermissionError("device must be unlocked")
        if profile is Profile.LAB:
            if operator_id is None or active_scope_id is None or expires_at is None:
                raise PermissionError("lab profile requires operator, scope and expiry")
            if not changed_at < expires_at <= changed_at + timedelta(minutes=30):
                raise PermissionError("lab profile expiry is invalid")
        elif expires_at is not None:
            raise ValueError("only lab profile may have an expiry")
        self._profile = ProfileState(
            active_profile=profile,
            indicator=f"PROFILE: {profile.value.upper()}",
            operator_id=operator_id if profile is Profile.LAB else None,
            scope_id=active_scope_id if profile is Profile.LAB else None,
            expires_at=expires_at,
        )
        return self._profile

    def tick(self, now: datetime) -> ProfileState:
        _require_aware(now)
        if self._profile.expires_at is not None and now >= self._profile.expires_at:
            self._reset_profile()
        return self._profile

    def reboot(self) -> ProfileState:
        self._reset_profile()
        return self._profile

    def capability_report_message(
        self,
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": 1,
            "device_id": self.device_id,
            "board_profile_id": self.board_profile.board_profile_id,
            "firmware_version": self.firmware_version,
            "generated_at": _timestamp(sent_at),
            "capabilities": sorted(self.board_profile.capabilities),
        }
        return self._message(
            "capability_report",
            payload,
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

    def profile_state_message(
        self,
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": 1,
            "active_profile": self._profile.active_profile.value,
            "indicator": self._profile.indicator,
            "operator_id": self._profile.operator_id,
            "scope_id": self._profile.scope_id,
            "expires_at": (
                _timestamp(self._profile.expires_at)
                if self._profile.expires_at is not None
                else None
            ),
        }
        return self._message(
            "profile_state",
            payload,
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

    def physical_cancel_message(
        self,
        job_id: str,
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": 1,
            "job_id": job_id,
            "input_source": "physical_cancel_key",
            "requested_at": _timestamp(sent_at),
        }
        return self._message(
            "cancel_request",
            payload,
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

    def voice_command_message(
        self,
        recorder: PushToTalkRecorder,
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        payload = recorder.payload()
        payload["active_profile"] = self._profile.active_profile.value
        return self._message(
            "voice_command",
            payload,
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

    def text_command_message(
        self,
        command: Mapping[str, object],
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        if command.get("profile") != self._profile.active_profile.value:
            raise PermissionError("command profile is not the visible active profile")
        return self._message(
            "text_command",
            dict(command),
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

    def _message(
        self,
        payload_type: str,
        payload: Mapping[str, object],
        *,
        sent_at: datetime,
        correlation_id: str,
    ) -> dict[str, object]:
        _require_aware(sent_at)
        self._sequence += 1
        unsigned: dict[str, object] = {
            "protocol_version": 1,
            "message_id": f"message:{self.boot_id}-{self._sequence}",
            "device_id": self.device_id,
            "sent_at": _timestamp(sent_at),
            "correlation_id": correlation_id,
            "sequence": self._sequence,
            "payload_type": payload_type,
            "payload": dict(payload),
        }
        return sign_envelope(
            unsigned,
            key_id=self.key_id,
            secret=self._secret,
        )

    def _reset_profile(self) -> None:
        self._profile = ProfileState(
            active_profile=Profile.ASSISTANT,
            indicator="PROFILE: ASSISTANT",
            operator_id=None,
            scope_id=None,
            expires_at=None,
        )


def _timestamp(value: datetime) -> str:
    _require_aware(value)
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

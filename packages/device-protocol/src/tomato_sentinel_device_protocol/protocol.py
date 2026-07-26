"""Canonical authenticated transport and replay protection for simulation."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .models import (
    DeviceIdentityState,
    DeviceIdentityStatus,
    ProvisionedDevice,
    VerifiedDeviceMessage,
)

MAXIMUM_ENVELOPE_BYTES = 32_768
MAXIMUM_REPLAY_IDS_PER_DEVICE = 1_024
MAXIMUM_KEY_ROTATIONS_PER_DEVICE = 64
_TYPED_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")


class DeviceMessageRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class DeviceRegistryChangeRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(slots=True)
class _RegistryEntry:
    device: ProvisionedDevice
    secret: bytes = field(repr=False)
    identity_revision: int = 1
    retired_key_ids: set[str] = field(default_factory=set)


class DeviceProtocolValidator:
    def __init__(
        self,
        *,
        envelope_schema: Mapping[str, Any],
        payload_schemas: Mapping[str, Mapping[str, Any]],
    ) -> None:
        Draft202012Validator.check_schema(envelope_schema)
        self._envelope = Draft202012Validator(
            envelope_schema,
            format_checker=FormatChecker(),
        )
        self._payloads: dict[str, Draft202012Validator] = {}
        for payload_type, schema in payload_schemas.items():
            Draft202012Validator.check_schema(schema)
            self._payloads[payload_type] = Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            )

    def validate_envelope(self, envelope: Mapping[str, object]) -> None:
        try:
            self._envelope.validate(envelope)
        except ValidationError as error:
            raise DeviceMessageRejectedError("ENVELOPE_SCHEMA_INVALID") from error

    def validate_payload(
        self,
        payload_type: str,
        payload: Mapping[str, object],
    ) -> None:
        validator = self._payloads.get(payload_type)
        if validator is None:
            raise DeviceMessageRejectedError("PAYLOAD_TYPE_NOT_REGISTERED")
        try:
            validator.validate(payload)
        except ValidationError as error:
            raise DeviceMessageRejectedError("PAYLOAD_SCHEMA_INVALID") from error


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, _RegistryEntry] = {}
        self._used_secret_fingerprints: set[bytes] = set()

    def provision(
        self,
        device: ProvisionedDevice,
        secret: bytes,
    ) -> DeviceIdentityStatus:
        if device.device_id in self._devices:
            raise DeviceRegistryChangeRejectedError("DEVICE_ALREADY_PROVISIONED")
        if device.revoked:
            raise DeviceRegistryChangeRejectedError("DEVICE_REVOKED")
        _validate_key_id(device.key_id)
        _validate_secret(secret)
        fingerprint = _secret_fingerprint(secret)
        if fingerprint in self._used_secret_fingerprints:
            raise DeviceRegistryChangeRejectedError("SECRET_REUSED")
        entry = _RegistryEntry(device=device, secret=bytes(secret))
        self._devices[device.device_id] = entry
        self._used_secret_fingerprints.add(fingerprint)
        return _status(entry)

    def status(self, device_id: str) -> DeviceIdentityStatus | None:
        entry = self._devices.get(device_id)
        return None if entry is None else _status(entry)

    def rotate_key(
        self,
        device_id: str,
        *,
        expected_key_id: str,
        new_key_id: str,
        new_secret: bytes,
    ) -> DeviceIdentityStatus:
        _validate_key_id(new_key_id)
        _validate_secret(new_secret)
        if new_key_id == expected_key_id:
            raise DeviceRegistryChangeRejectedError("KEY_ID_UNCHANGED")

        entry = self._require_entry(device_id)
        if entry.device.revoked:
            raise DeviceRegistryChangeRejectedError("DEVICE_REVOKED")
        if entry.device.key_id == new_key_id:
            if hmac.compare_digest(entry.secret, new_secret):
                return _status(entry)
            raise DeviceRegistryChangeRejectedError("KEY_ID_COLLISION")
        if entry.device.key_id != expected_key_id:
            raise DeviceRegistryChangeRejectedError("KEY_ID_MISMATCH")
        if new_key_id in entry.retired_key_ids:
            raise DeviceRegistryChangeRejectedError("KEY_ID_RETIRED")
        if len(entry.retired_key_ids) >= MAXIMUM_KEY_ROTATIONS_PER_DEVICE:
            raise DeviceRegistryChangeRejectedError("KEY_ROTATION_LIMIT_REACHED")
        if hmac.compare_digest(entry.secret, new_secret):
            raise DeviceRegistryChangeRejectedError("SECRET_UNCHANGED")
        fingerprint = _secret_fingerprint(new_secret)
        if fingerprint in self._used_secret_fingerprints:
            raise DeviceRegistryChangeRejectedError("SECRET_REUSED")

        entry.retired_key_ids.add(entry.device.key_id)
        entry.device = replace(entry.device, key_id=new_key_id)
        entry.secret = bytes(new_secret)
        entry.identity_revision += 1
        self._used_secret_fingerprints.add(fingerprint)
        return _status(entry)

    def revoke(
        self,
        device_id: str,
        *,
        expected_key_id: str,
    ) -> DeviceIdentityStatus:
        entry = self._require_entry(device_id)
        if entry.device.key_id != expected_key_id:
            raise DeviceRegistryChangeRejectedError("KEY_ID_MISMATCH")
        if entry.device.revoked:
            return _status(entry)

        entry.device = replace(entry.device, revoked=True)
        entry.identity_revision += 1
        return _status(entry)

    def _require_entry(self, device_id: str) -> _RegistryEntry:
        entry = self._devices.get(device_id)
        if entry is None:
            raise DeviceRegistryChangeRejectedError("DEVICE_UNKNOWN")
        return entry

    def _lookup(self, device_id: str) -> tuple[ProvisionedDevice, bytes] | None:
        entry = self._devices.get(device_id)
        if entry is None:
            return None
        return entry.device, entry.secret


class DeviceMessageVerifier:
    def __init__(
        self,
        validator: DeviceProtocolValidator,
        registry: DeviceRegistry,
    ) -> None:
        self._validator = validator
        self._registry = registry
        self._message_ids: dict[tuple[str, str], set[str]] = {}
        self._message_order: dict[tuple[str, str], deque[str]] = {}
        self._last_sequences: dict[tuple[str, str], int] = {}

    def verify(
        self,
        envelope: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> VerifiedDeviceMessage:
        _require_aware(received_at)
        encoded = _encode(envelope)
        if len(encoded) > MAXIMUM_ENVELOPE_BYTES:
            raise DeviceMessageRejectedError("MESSAGE_TOO_LARGE")
        if envelope.get("protocol_version") != 1:
            raise DeviceMessageRejectedError("PROTOCOL_VERSION_UNSUPPORTED")
        self._validator.validate_envelope(envelope)

        device_id = cast(str, envelope["device_id"])
        registered = self._registry._lookup(device_id)
        if registered is None:
            raise DeviceMessageRejectedError("DEVICE_UNKNOWN")
        device, secret = registered
        if device.revoked:
            raise DeviceMessageRejectedError("DEVICE_REVOKED")

        authentication = cast(Mapping[str, object], envelope["authentication"])
        if authentication["key_id"] != device.key_id:
            raise DeviceMessageRejectedError("KEY_ID_MISMATCH")
        supplied_tag = cast(str, authentication["tag"])
        expected_tag = _authentication_tag(envelope, secret)
        if not hmac.compare_digest(supplied_tag, expected_tag):
            raise DeviceMessageRejectedError("AUTHENTICATION_INVALID")

        sent_at = datetime.fromisoformat(
            cast(str, envelope["sent_at"]).replace("Z", "+00:00")
        )
        if not (
            received_at - timedelta(minutes=5)
            <= sent_at
            <= received_at + timedelta(seconds=30)
        ):
            raise DeviceMessageRejectedError("MESSAGE_TIMESTAMP_INVALID")

        payload_type = cast(str, envelope["payload_type"])
        payload = cast(Mapping[str, object], envelope["payload"])
        self._validator.validate_payload(payload_type, payload)
        if payload_type == "capability_report":
            _verify_capability_report(payload, device)
        elif payload_type == "voice_command":
            _verify_voice_command(payload, device)

        message_id = cast(str, envelope["message_id"])
        replay_identity = (device_id, device.key_id)
        device_message_ids = self._message_ids.setdefault(replay_identity, set())
        if message_id in device_message_ids:
            raise DeviceMessageRejectedError("MESSAGE_ID_REPLAYED")
        sequence = cast(int, envelope["sequence"])
        if sequence <= self._last_sequences.get(replay_identity, 0):
            raise DeviceMessageRejectedError("SEQUENCE_REPLAYED")

        message_order = self._message_order.setdefault(replay_identity, deque())
        if len(message_order) >= MAXIMUM_REPLAY_IDS_PER_DEVICE:
            device_message_ids.remove(message_order.popleft())
        message_order.append(message_id)
        device_message_ids.add(message_id)
        self._last_sequences[replay_identity] = sequence
        return VerifiedDeviceMessage(
            message_id=message_id,
            device_id=device_id,
            sent_at=sent_at,
            correlation_id=cast(str, envelope["correlation_id"]),
            sequence=sequence,
            payload_type=payload_type,
            payload=dict(payload),
        )


def sign_envelope(
    unsigned_envelope: Mapping[str, object],
    *,
    key_id: str,
    secret: bytes,
) -> dict[str, object]:
    envelope = {
        **unsigned_envelope,
        "authentication": {
            "algorithm": "simulation_hmac_sha256",
            "key_id": key_id,
            "tag": "0" * 64,
        },
    }
    tag = _authentication_tag(envelope, secret)
    authentication = cast(dict[str, object], envelope["authentication"])
    authentication["tag"] = tag
    return envelope


def _authentication_tag(
    envelope: Mapping[str, object],
    secret: bytes,
) -> str:
    material = _signing_material(envelope)
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def _signing_material(envelope: Mapping[str, object]) -> bytes:
    authentication = cast(Mapping[str, object], envelope["authentication"])
    unsigned = {
        key: value for key, value in envelope.items() if key != "authentication"
    }
    unsigned["authentication"] = {
        "algorithm": authentication["algorithm"],
        "key_id": authentication["key_id"],
    }
    return _encode(unsigned)


def _encode(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise DeviceMessageRejectedError("MESSAGE_NOT_CANONICAL_JSON") from error


def _verify_capability_report(
    payload: Mapping[str, object],
    device: ProvisionedDevice,
) -> None:
    capabilities = frozenset(cast(list[str], payload["capabilities"]))
    if (
        payload["device_id"] != device.device_id
        or payload["board_profile_id"] != device.board_profile.board_profile_id
        or payload["firmware_version"] != device.firmware_version
        or capabilities != device.board_profile.capabilities
    ):
        raise DeviceMessageRejectedError("CAPABILITY_REPORT_MISMATCH")


def _verify_voice_command(
    payload: Mapping[str, object],
    device: ProvisionedDevice,
) -> None:
    if "microphone" not in device.board_profile.capabilities:
        raise DeviceMessageRejectedError("MICROPHONE_CAPABILITY_REQUIRED")
    audio = cast(Mapping[str, object], payload["audio"])
    try:
        content = base64.b64decode(
            cast(str, audio["content_base64"]),
            validate=True,
        )
    except (binascii.Error, ValueError) as error:
        raise DeviceMessageRejectedError("AUDIO_CONTENT_INVALID") from error
    if len(content) != audio["byte_length"]:
        raise DeviceMessageRejectedError("AUDIO_LENGTH_MISMATCH")
    recorded_at = datetime.fromisoformat(
        cast(str, payload["recorded_at"]).replace("Z", "+00:00")
    )
    completed_at = datetime.fromisoformat(
        cast(str, payload["completed_at"]).replace("Z", "+00:00")
    )
    if completed_at < recorded_at:
        raise DeviceMessageRejectedError("AUDIO_TIMESTAMP_INVALID")


def _validate_key_id(key_id: str) -> None:
    if len(key_id) > 160 or _TYPED_IDENTIFIER.fullmatch(key_id) is None:
        raise DeviceRegistryChangeRejectedError("KEY_ID_INVALID")


def _validate_secret(secret: bytes) -> None:
    if len(secret) < 32:
        raise DeviceRegistryChangeRejectedError("SECRET_TOO_SHORT")


def _secret_fingerprint(secret: bytes) -> bytes:
    return hashlib.sha256(secret).digest()


def _status(entry: _RegistryEntry) -> DeviceIdentityStatus:
    device = entry.device
    state = (
        DeviceIdentityState.REVOKED if device.revoked else DeviceIdentityState.TRUSTED
    )
    return DeviceIdentityStatus(
        device_id=device.device_id,
        key_id=device.key_id,
        board_profile_id=device.board_profile.board_profile_id,
        firmware_version=device.firmware_version,
        identity_revision=entry.identity_revision,
        state=state,
    )


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

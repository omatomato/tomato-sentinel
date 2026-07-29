"""RAM-only simulation of a physically verified Tomato Link pairing ceremony."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

MINIMUM_PAIRING_TTL = timedelta(seconds=30)
MAXIMUM_PAIRING_TTL = timedelta(seconds=120)
PAIRING_ROOT_BYTES = 32
PAIRING_PUBLIC_KEY_BYTES = 32
PAIRING_FINGERPRINT_BYTES = 16
_TYPED_ID = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
_HKDF_INFO = b"tomato-sentinel/tomato-link/ephemeral-root/v1"


class PairingRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class PairingRole(StrEnum):
    DEVICE = "device"
    EDGE = "edge"


class PairingState(StrEnum):
    OFFERED = "offered"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ESTABLISHED = "established"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PairingRoute:
    organization_id: str
    source_endpoint_id: str
    destination_endpoint_id: str


@dataclass(frozen=True, slots=True)
class PairingStatus:
    ceremony_id: str
    participant_role: PairingRole
    state: PairingState
    fingerprint: str | None
    expires_at: datetime
    reason_code: str | None

    def to_contract(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "ceremony_id": self.ceremony_id,
            "participant_role": self.participant_role.value,
            "state": self.state.value,
            "fingerprint": self.fingerprint,
            "expires_at": _format_timestamp(self.expires_at),
            "reason_code": self.reason_code,
            "execution_mode": "simulation",
        }


@dataclass(slots=True)
class EphemeralPairingParticipant:
    """One endpoint of a short, display-confirmed, one-shot pairing ceremony."""

    hello_schema: Mapping[str, object] = field(repr=False)
    route: PairingRoute
    role: PairingRole
    ceremony_id: str
    boot_id: str
    created_at: datetime
    ttl: timedelta
    private_key: X25519PrivateKey | None = field(
        default_factory=X25519PrivateKey.generate,
        repr=False,
    )
    _state: PairingState = field(init=False, default=PairingState.OFFERED)
    _reason_code: str | None = field(init=False, default=None, repr=False)
    _peer_hello: dict[str, object] | None = field(init=False, default=None, repr=False)
    _transcript_hash: bytes | None = field(init=False, default=None, repr=False)
    _fingerprint: str | None = field(init=False, default=None)
    _root_secret: bytearray | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        _require_aware(self.created_at)
        _validate_route(self.route)
        _validate_typed_id(self.ceremony_id, "PAIRING_CEREMONY_ID_INVALID")
        _validate_typed_id(self.boot_id, "PAIRING_BOOT_ID_INVALID")
        if self.private_key is None:
            raise PairingRejectedError("PAIRING_PRIVATE_KEY_REQUIRED")
        if not MINIMUM_PAIRING_TTL <= self.ttl <= MAXIMUM_PAIRING_TTL:
            raise PairingRejectedError("PAIRING_TTL_INVALID")
        Draft202012Validator.check_schema(self.hello_schema)

    @property
    def expires_at(self) -> datetime:
        return self.created_at + self.ttl

    @property
    def status(self) -> PairingStatus:
        return PairingStatus(
            ceremony_id=self.ceremony_id,
            participant_role=self.role,
            state=self._state,
            fingerprint=self._fingerprint,
            expires_at=self.expires_at,
            reason_code=self._reason_code,
        )

    def hello(self) -> dict[str, object]:
        self._require_not_terminal()
        assert self.private_key is not None
        public_key = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        contract: dict[str, object] = {
            "contract_version": 1,
            "pairing_version": 1,
            "ceremony_id": self.ceremony_id,
            "participant_role": self.role.value,
            "organization_id": self.route.organization_id,
            "source_endpoint_id": self.route.source_endpoint_id,
            "destination_endpoint_id": self.route.destination_endpoint_id,
            "boot_id": self.boot_id,
            "ephemeral_public_key_base64": base64.b64encode(public_key).decode("ascii"),
            "created_at": _format_timestamp(self.created_at),
            "expires_at": _format_timestamp(self.expires_at),
            "execution_mode": "simulation",
        }
        return deepcopy(contract)

    def receive_peer_hello(
        self,
        contract: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> str:
        self._require_live(received_at)
        candidate = deepcopy(dict(contract))
        try:
            Draft202012Validator(
                self.hello_schema,
                format_checker=FormatChecker(),
            ).validate(candidate)
        except ValidationError as error:
            raise PairingRejectedError("PAIRING_HELLO_INVALID") from error
        self._validate_peer_fields(candidate, received_at=received_at)
        if self._peer_hello is not None:
            if candidate == self._peer_hello:
                assert self._fingerprint is not None
                return self._fingerprint
            raise PairingRejectedError("PAIRING_PEER_HELLO_CHANGED")

        transcript = _canonical_transcript(self.hello(), candidate)
        transcript_hash = hashlib.sha256(transcript).digest()
        self._peer_hello = candidate
        self._transcript_hash = transcript_hash
        self._fingerprint = _format_fingerprint(
            transcript_hash[:PAIRING_FINGERPRINT_BYTES]
        )
        self._state = PairingState.AWAITING_CONFIRMATION
        return self._fingerprint

    def confirm_fingerprint(
        self,
        fingerprint: str,
        *,
        confirmed_at: datetime,
        confirmation_source: str,
    ) -> PairingStatus:
        self._require_live(confirmed_at)
        if self._state is not PairingState.AWAITING_CONFIRMATION:
            raise PairingRejectedError("PAIRING_NOT_AWAITING_CONFIRMATION")
        if confirmation_source != "physical_display":
            raise PairingRejectedError("PAIRING_CONFIRMATION_SOURCE_INVALID")
        assert self._fingerprint is not None
        if not hmac.compare_digest(fingerprint, self._fingerprint):
            raise PairingRejectedError("PAIRING_FINGERPRINT_MISMATCH")
        assert self._peer_hello is not None
        assert self._transcript_hash is not None
        assert self.private_key is not None
        peer_public_key = _decode_public_key(self._peer_hello)
        try:
            shared_secret = self.private_key.exchange(peer_public_key)
        except ValueError as error:
            raise PairingRejectedError("PAIRING_SHARED_SECRET_INVALID") from error
        root_secret = HKDF(
            algorithm=hashes.SHA256(),
            length=PAIRING_ROOT_BYTES,
            salt=self._transcript_hash,
            info=_HKDF_INFO,
        ).derive(shared_secret)
        self._root_secret = bytearray(root_secret)
        self._state = PairingState.ESTABLISHED
        return self.status

    def consume_root_secret(
        self,
        sink: Callable[[str, bytes], object],
        *,
        consumed_at: datetime,
    ) -> object:
        self._require_live(consumed_at)
        if self._state is not PairingState.ESTABLISHED:
            raise PairingRejectedError("PAIRING_ROOT_NOT_AVAILABLE")
        assert self._root_secret is not None
        assert self._transcript_hash is not None
        key_id = f"link-root-key:{self._transcript_hash.hex()[:16]}"
        result = sink(key_id, bytes(self._root_secret))
        self._clear_secrets()
        self._state = PairingState.CONSUMED
        return result

    def cancel(self, *, reason_code: str = "PAIRING_CANCELLED") -> PairingStatus:
        if self._state in {
            PairingState.CONSUMED,
            PairingState.CANCELLED,
            PairingState.EXPIRED,
        }:
            return self.status
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code):
            raise PairingRejectedError("PAIRING_REASON_CODE_INVALID")
        self._clear_secrets()
        self._state = PairingState.CANCELLED
        self._reason_code = reason_code
        return self.status

    def expire(self, *, now: datetime) -> PairingStatus:
        _require_aware(now)
        if now < self.expires_at:
            raise PairingRejectedError("PAIRING_NOT_EXPIRED")
        if self._state not in {
            PairingState.CONSUMED,
            PairingState.CANCELLED,
            PairingState.EXPIRED,
        }:
            self._clear_secrets()
            self._state = PairingState.EXPIRED
            self._reason_code = "PAIRING_WINDOW_EXPIRED"
        return self.status

    def reset_for_reboot(self) -> PairingStatus:
        return self.cancel(reason_code="PAIRING_BOOT_CHANGED")

    def _validate_peer_fields(
        self,
        contract: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> None:
        expected_role = (
            PairingRole.EDGE if self.role is PairingRole.DEVICE else PairingRole.DEVICE
        )
        exact_fields = {
            "ceremony_id": self.ceremony_id,
            "organization_id": self.route.organization_id,
            "source_endpoint_id": self.route.source_endpoint_id,
            "destination_endpoint_id": self.route.destination_endpoint_id,
            "execution_mode": "simulation",
        }
        if contract["participant_role"] != expected_role.value:
            raise PairingRejectedError("PAIRING_PEER_ROLE_INVALID")
        if any(contract[name] != value for name, value in exact_fields.items()):
            raise PairingRejectedError("PAIRING_ROUTE_MISMATCH")
        created_at = _parse_timestamp(cast(str, contract["created_at"]))
        expires_at = _parse_timestamp(cast(str, contract["expires_at"]))
        peer_ttl = expires_at - created_at
        if not MINIMUM_PAIRING_TTL <= peer_ttl <= MAXIMUM_PAIRING_TTL:
            raise PairingRejectedError("PAIRING_PEER_WINDOW_INVALID")
        if received_at < created_at or received_at >= expires_at:
            raise PairingRejectedError("PAIRING_PEER_EXPIRED")
        own_public = cast(str, self.hello()["ephemeral_public_key_base64"])
        if hmac.compare_digest(
            cast(str, contract["ephemeral_public_key_base64"]),
            own_public,
        ):
            raise PairingRejectedError("PAIRING_REFLECTED_KEY")
        _decode_public_key(contract)

    def _require_live(self, now: datetime) -> None:
        _require_aware(now)
        self._require_not_terminal()
        if now < self.created_at:
            raise PairingRejectedError("PAIRING_NOT_STARTED")
        if now >= self.expires_at:
            self.expire(now=now)
            raise PairingRejectedError("PAIRING_WINDOW_EXPIRED")

    def _require_not_terminal(self) -> None:
        if self._state in {
            PairingState.CONSUMED,
            PairingState.CANCELLED,
            PairingState.EXPIRED,
        }:
            raise PairingRejectedError("PAIRING_TERMINAL")

    def _clear_secrets(self) -> None:
        if self._root_secret is not None:
            self._root_secret[:] = b"\x00" * len(self._root_secret)
        self._root_secret = None
        self.private_key = None


def _canonical_transcript(
    first: Mapping[str, object],
    second: Mapping[str, object],
) -> bytes:
    by_role = {
        cast(str, first["participant_role"]): dict(first),
        cast(str, second["participant_role"]): dict(second),
    }
    if set(by_role) != {PairingRole.DEVICE.value, PairingRole.EDGE.value}:
        raise PairingRejectedError("PAIRING_TRANSCRIPT_ROLES_INVALID")
    return json.dumps(
        {
            "transcript_version": 1,
            "device_hello": by_role[PairingRole.DEVICE.value],
            "edge_hello": by_role[PairingRole.EDGE.value],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _decode_public_key(contract: Mapping[str, object]) -> X25519PublicKey:
    try:
        decoded = base64.b64decode(
            cast(str, contract["ephemeral_public_key_base64"]),
            validate=True,
        )
    except (ValueError, binascii.Error) as error:
        raise PairingRejectedError("PAIRING_PUBLIC_KEY_INVALID") from error
    if len(decoded) != PAIRING_PUBLIC_KEY_BYTES:
        raise PairingRejectedError("PAIRING_PUBLIC_KEY_INVALID")
    try:
        return X25519PublicKey.from_public_bytes(decoded)
    except ValueError as error:
        raise PairingRejectedError("PAIRING_PUBLIC_KEY_INVALID") from error


def _format_fingerprint(value: bytes) -> str:
    encoded = value.hex()
    return "-".join(encoded[index : index + 4] for index in range(0, 32, 4))


def _validate_route(route: PairingRoute) -> None:
    for value in (
        route.organization_id,
        route.source_endpoint_id,
        route.destination_endpoint_id,
    ):
        _validate_typed_id(value, "PAIRING_ROUTE_INVALID")
    if route.source_endpoint_id == route.destination_endpoint_id:
        raise PairingRejectedError("PAIRING_ROUTE_INVALID")


def _validate_typed_id(value: str, reason_code: str) -> None:
    if len(value) > 160 or not _TYPED_ID.fullmatch(value):
        raise PairingRejectedError(reason_code)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PairingRejectedError("PAIRING_TIMEZONE_REQUIRED")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PairingRejectedError("PAIRING_TIMESTAMP_INVALID") from error
    _require_aware(parsed)
    return parsed

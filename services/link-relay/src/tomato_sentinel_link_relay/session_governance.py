"""Simulation-only credential lifecycle and short Tomato Link session leases."""

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from collections import deque
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .sealed_payload import (
    TomatoLinkSealedPayloadCodec,
    TomatoLinkSealingBinding,
    TomatoLinkSessionKey,
)

MINIMUM_ROOT_SECRET_BYTES = 32
SESSION_SALT_BYTES = 32
MINIMUM_SESSION_TTL = timedelta(seconds=10)
MAXIMUM_SESSION_TTL = timedelta(seconds=120)
MAXIMUM_SESSION_CLOCK_SKEW = timedelta(seconds=30)
MAXIMUM_RETIRED_LINK_KEYS = 64
MAXIMUM_LEASE_RECORDS = 1_024
_TYPED_ID = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")


class LinkSessionRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class LinkCredentialState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class LinkRoute:
    organization_id: str
    source_endpoint_id: str
    destination_endpoint_id: str


@dataclass(frozen=True, slots=True)
class LinkCredentialStatus:
    route: LinkRoute
    key_id: str
    identity_revision: int
    state: LinkCredentialState


@dataclass(slots=True)
class _CredentialEntry:
    route: LinkRoute
    key_id: str
    secret: bytes = field(repr=False)
    identity_revision: int = 1
    state: LinkCredentialState = LinkCredentialState.ACTIVE
    retired_key_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class LinkSessionLease:
    lease_id: str
    session_id: str
    route: LinkRoute
    key_id: str
    identity_revision: int
    salt: bytes = field(repr=False)
    issued_at: datetime
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "LinkSessionLease("
            f"lease_id={self.lease_id!r}, "
            f"session_id={self.session_id!r}, "
            f"route={self.route!r}, "
            f"key_id={self.key_id!r}, "
            f"identity_revision={self.identity_revision!r}, "
            "salt=<redacted>, "
            f"issued_at={self.issued_at!r}, "
            f"expires_at={self.expires_at!r})"
        )

    def to_unsigned_contract(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "lease_id": self.lease_id,
            "session_id": self.session_id,
            "organization_id": self.route.organization_id,
            "source_endpoint_id": self.route.source_endpoint_id,
            "destination_endpoint_id": self.route.destination_endpoint_id,
            "key_id": self.key_id,
            "identity_revision": self.identity_revision,
            "derivation_algorithm": "HKDF-SHA256",
            "salt_base64": base64.b64encode(self.salt).decode("ascii"),
            "issued_at": _format_timestamp(self.issued_at),
            "expires_at": _format_timestamp(self.expires_at),
            "execution_mode": "simulation",
        }


@dataclass(frozen=True, slots=True)
class ManagedLinkSession:
    lease: LinkSessionLease
    _lease_contract: Mapping[str, object] = field(repr=False)
    session_key: TomatoLinkSessionKey = field(repr=False)

    def __repr__(self) -> str:
        return f"ManagedLinkSession(lease={self.lease!r}, session_key=<redacted>)"

    @property
    def lease_contract(self) -> Mapping[str, object]:
        return cast(dict[str, object], deepcopy(self._lease_contract))


class InMemoryLinkCredentialVault:
    """Fake vault with separate per-route Tomato Link root credentials."""

    def __init__(self) -> None:
        self._entries: dict[LinkRoute, _CredentialEntry] = {}
        self._secret_fingerprints: set[bytes] = set()

    def provision(
        self,
        route: LinkRoute,
        *,
        key_id: str,
        secret: bytes,
    ) -> LinkCredentialStatus:
        if route in self._entries:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_ALREADY_PROVISIONED")
        _validate_route(route)
        _validate_typed_id(key_id, "LINK_CREDENTIAL_KEY_ID_INVALID")
        _validate_root_secret(secret)
        fingerprint = _secret_fingerprint(secret)
        if fingerprint in self._secret_fingerprints:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_SECRET_REUSED")
        entry = _CredentialEntry(route=route, key_id=key_id, secret=bytes(secret))
        self._entries[route] = entry
        self._secret_fingerprints.add(fingerprint)
        return _credential_status(entry)

    def status(self, route: LinkRoute) -> LinkCredentialStatus | None:
        entry = self._entries.get(route)
        return None if entry is None else _credential_status(entry)

    def rotate(
        self,
        route: LinkRoute,
        *,
        expected_key_id: str,
        new_key_id: str,
        new_secret: bytes,
    ) -> LinkCredentialStatus:
        entry = self._require_entry(route)
        if entry.state is LinkCredentialState.REVOKED:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_REVOKED")
        _validate_root_secret(new_secret)
        _validate_typed_id(new_key_id, "LINK_CREDENTIAL_KEY_ID_INVALID")
        if entry.key_id == new_key_id:
            if entry.key_id != expected_key_id:
                if hmac.compare_digest(entry.secret, new_secret):
                    return _credential_status(entry)
                raise LinkSessionRejectedError("LINK_CREDENTIAL_KEY_ID_COLLISION")
            raise LinkSessionRejectedError("LINK_CREDENTIAL_KEY_ID_UNCHANGED")
        if entry.key_id != expected_key_id:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_KEY_ID_MISMATCH")
        if new_key_id in entry.retired_key_ids:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_KEY_ID_RETIRED")
        if len(entry.retired_key_ids) >= MAXIMUM_RETIRED_LINK_KEYS:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_ROTATION_LIMIT")
        if hmac.compare_digest(entry.secret, new_secret):
            raise LinkSessionRejectedError("LINK_CREDENTIAL_SECRET_UNCHANGED")
        fingerprint = _secret_fingerprint(new_secret)
        if fingerprint in self._secret_fingerprints:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_SECRET_REUSED")

        entry.retired_key_ids.add(entry.key_id)
        entry.key_id = new_key_id
        entry.secret = bytes(new_secret)
        entry.identity_revision += 1
        self._secret_fingerprints.add(fingerprint)
        return _credential_status(entry)

    def revoke(
        self,
        route: LinkRoute,
        *,
        expected_key_id: str,
    ) -> LinkCredentialStatus:
        entry = self._require_entry(route)
        if entry.key_id != expected_key_id:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_KEY_ID_MISMATCH")
        if entry.state is LinkCredentialState.REVOKED:
            return _credential_status(entry)
        entry.state = LinkCredentialState.REVOKED
        entry.identity_revision += 1
        return _credential_status(entry)

    def derive_session_key(self, lease: LinkSessionLease) -> TomatoLinkSessionKey:
        entry = self._require_entry(lease.route)
        if entry.state is LinkCredentialState.REVOKED:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_REVOKED")
        if (
            entry.key_id != lease.key_id
            or entry.identity_revision != lease.identity_revision
        ):
            raise LinkSessionRejectedError("LINK_SESSION_IDENTITY_STALE")
        info = _canonical_json(
            {
                "derivation_version": 1,
                "destination_endpoint_id": lease.route.destination_endpoint_id,
                "identity_revision": lease.identity_revision,
                "key_id": lease.key_id,
                "lease_id": lease.lease_id,
                "organization_id": lease.route.organization_id,
                "session_id": lease.session_id,
                "source_endpoint_id": lease.route.source_endpoint_id,
            }
        )
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=lease.salt,
            info=info,
        ).derive(entry.secret)
        return TomatoLinkSessionKey(
            key_id=lease.key_id,
            organization_id=lease.route.organization_id,
            source_endpoint_id=lease.route.source_endpoint_id,
            destination_endpoint_id=lease.route.destination_endpoint_id,
            session_id=lease.session_id,
            key=key,
        )

    def authenticate_lease(self, lease: LinkSessionLease) -> str:
        entry = self._require_entry(lease.route)
        if entry.state is LinkCredentialState.REVOKED:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_REVOKED")
        if (
            entry.key_id != lease.key_id
            or entry.identity_revision != lease.identity_revision
        ):
            raise LinkSessionRejectedError("LINK_SESSION_IDENTITY_STALE")
        return hmac.new(
            entry.secret,
            _canonical_json(lease.to_unsigned_contract()),
            hashlib.sha256,
        ).hexdigest()

    def verify_lease_contract(self, contract: Mapping[str, object]) -> None:
        lease = _lease_from_contract(contract)
        authentication = cast(Mapping[str, object], contract["authentication"])
        expected = self.authenticate_lease(lease)
        if not hmac.compare_digest(cast(str, authentication["tag"]), expected):
            raise LinkSessionRejectedError("LINK_SESSION_AUTHENTICATION_INVALID")

    def require_session_active(
        self,
        session: ManagedLinkSession,
        *,
        now: datetime,
    ) -> None:
        self.active_session_key(session, now=now)

    def active_session_key(
        self,
        session: ManagedLinkSession,
        *,
        now: datetime,
    ) -> TomatoLinkSessionKey:
        _require_aware(now)
        if now < session.lease.issued_at or now >= session.lease.expires_at:
            raise LinkSessionRejectedError("LINK_SESSION_EXPIRED")
        return self.derive_session_key(session.lease)

    def _require_entry(self, route: LinkRoute) -> _CredentialEntry:
        entry = self._entries.get(route)
        if entry is None:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_UNKNOWN")
        return entry


class LinkSessionAuthority:
    def __init__(
        self,
        schema: Mapping[str, Any],
        vault: InMemoryLinkCredentialVault,
        *,
        salt_source: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
        self._vault = vault
        self._salt_source = salt_source
        self._records: dict[str, tuple[str, ManagedLinkSession]] = {}
        self._record_order: deque[str] = deque()

    def issue(
        self,
        *,
        lease_id: str,
        session_id: str,
        route: LinkRoute,
        now: datetime,
        ttl: timedelta,
    ) -> ManagedLinkSession:
        _require_aware(now)
        if not MINIMUM_SESSION_TTL <= ttl <= MAXIMUM_SESSION_TTL:
            raise LinkSessionRejectedError("LINK_SESSION_TTL_INVALID")
        status = self._vault.status(route)
        if status is None:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_UNKNOWN")
        if status.state is LinkCredentialState.REVOKED:
            raise LinkSessionRejectedError("LINK_CREDENTIAL_REVOKED")
        request_fingerprint = _fingerprint(
            {
                "lease_id": lease_id,
                "session_id": session_id,
                "route": {
                    "organization_id": route.organization_id,
                    "source_endpoint_id": route.source_endpoint_id,
                    "destination_endpoint_id": route.destination_endpoint_id,
                },
                "issued_at": _format_timestamp(now),
                "expires_at": _format_timestamp(now + ttl),
            }
        )
        existing = self._records.get(lease_id)
        if existing is not None:
            if existing[0] != request_fingerprint:
                raise LinkSessionRejectedError("LINK_SESSION_LEASE_ID_REUSED")
            self._vault.require_session_active(existing[1], now=now)
            return existing[1]

        salt = self._salt_source(SESSION_SALT_BYTES)
        if len(salt) != SESSION_SALT_BYTES:
            raise LinkSessionRejectedError("LINK_SESSION_SALT_LENGTH_INVALID")
        lease = LinkSessionLease(
            lease_id=lease_id,
            session_id=session_id,
            route=route,
            key_id=status.key_id,
            identity_revision=status.identity_revision,
            salt=bytes(salt),
            issued_at=now,
            expires_at=now + ttl,
        )
        contract = _authenticated_contract(
            lease,
            self._vault.authenticate_lease(lease),
        )
        self._validate_contract(contract, received_at=now)
        session = ManagedLinkSession(
            lease=lease,
            _lease_contract=contract,
            session_key=self._vault.derive_session_key(lease),
        )
        self._remember(lease_id, request_fingerprint, session)
        return session

    def accept(
        self,
        contract: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> ManagedLinkSession:
        self._validate_contract(contract, received_at=received_at)
        self._vault.verify_lease_contract(contract)
        lease = _lease_from_contract(contract)
        fingerprint = _fingerprint(contract)
        existing = self._records.get(lease.lease_id)
        if existing is not None:
            if existing[0] != fingerprint:
                raise LinkSessionRejectedError("LINK_SESSION_LEASE_ID_REUSED")
            self._vault.require_session_active(existing[1], now=received_at)
            return existing[1]
        session = ManagedLinkSession(
            lease=lease,
            _lease_contract=dict(contract),
            session_key=self._vault.derive_session_key(lease),
        )
        self._remember(lease.lease_id, fingerprint, session)
        return session

    def _validate_contract(
        self,
        contract: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> None:
        _require_aware(received_at)
        try:
            self._validator.validate(contract)
        except ValidationError as error:
            raise LinkSessionRejectedError("LINK_SESSION_SCHEMA_INVALID") from error
        issued_at = _timestamp(cast(str, contract["issued_at"]))
        expires_at = _timestamp(cast(str, contract["expires_at"]))
        duration = expires_at - issued_at
        if (
            not MINIMUM_SESSION_TTL <= duration <= MAXIMUM_SESSION_TTL
            or issued_at > received_at + MAXIMUM_SESSION_CLOCK_SKEW
            or received_at >= expires_at
        ):
            raise LinkSessionRejectedError("LINK_SESSION_TIME_INVALID")
        salt = _decode_salt(cast(str, contract["salt_base64"]))
        if len(salt) != SESSION_SALT_BYTES:
            raise LinkSessionRejectedError("LINK_SESSION_SALT_LENGTH_INVALID")

    def _remember(
        self,
        lease_id: str,
        fingerprint: str,
        session: ManagedLinkSession,
    ) -> None:
        if len(self._record_order) >= MAXIMUM_LEASE_RECORDS:
            expired = self._record_order.popleft()
            self._records.pop(expired, None)
        self._record_order.append(lease_id)
        self._records[lease_id] = (fingerprint, session)


class GovernedTomatoLinkCodec:
    """Checks current credential state before every cryptographic operation."""

    def __init__(
        self,
        codec: TomatoLinkSealedPayloadCodec,
        vault: InMemoryLinkCredentialVault,
    ) -> None:
        self._codec = codec
        self._vault = vault

    def seal(
        self,
        plaintext: bytes,
        *,
        binding: TomatoLinkSealingBinding,
        session: ManagedLinkSession,
        now: datetime,
    ) -> bytes:
        current_key = self._vault.active_session_key(session, now=now)
        return self._codec.seal(
            plaintext,
            binding=binding,
            session_key=current_key,
        )

    def open(
        self,
        sealed_payload: bytes,
        *,
        binding: TomatoLinkSealingBinding,
        session: ManagedLinkSession,
        now: datetime,
    ) -> bytes:
        current_key = self._vault.active_session_key(session, now=now)
        return self._codec.open(
            sealed_payload,
            binding=binding,
            session_key=current_key,
        )


def _lease_from_contract(contract: Mapping[str, object]) -> LinkSessionLease:
    return LinkSessionLease(
        lease_id=cast(str, contract["lease_id"]),
        session_id=cast(str, contract["session_id"]),
        route=LinkRoute(
            organization_id=cast(str, contract["organization_id"]),
            source_endpoint_id=cast(str, contract["source_endpoint_id"]),
            destination_endpoint_id=cast(str, contract["destination_endpoint_id"]),
        ),
        key_id=cast(str, contract["key_id"]),
        identity_revision=cast(int, contract["identity_revision"]),
        salt=_decode_salt(cast(str, contract["salt_base64"])),
        issued_at=_timestamp(cast(str, contract["issued_at"])),
        expires_at=_timestamp(cast(str, contract["expires_at"])),
    )


def _authenticated_contract(
    lease: LinkSessionLease,
    authentication_tag: str,
) -> dict[str, object]:
    return {
        **lease.to_unsigned_contract(),
        "authentication": {
            "algorithm": "simulation_hmac_sha256",
            "tag": authentication_tag,
        },
    }


def _credential_status(entry: _CredentialEntry) -> LinkCredentialStatus:
    return LinkCredentialStatus(
        route=entry.route,
        key_id=entry.key_id,
        identity_revision=entry.identity_revision,
        state=entry.state,
    )


def _validate_root_secret(secret: bytes) -> None:
    if len(secret) < MINIMUM_ROOT_SECRET_BYTES:
        raise LinkSessionRejectedError("LINK_CREDENTIAL_SECRET_TOO_SHORT")


def _validate_route(route: LinkRoute) -> None:
    for value in (
        route.organization_id,
        route.source_endpoint_id,
        route.destination_endpoint_id,
    ):
        _validate_typed_id(value, "LINK_CREDENTIAL_ROUTE_INVALID")


def _validate_typed_id(value: str, reason_code: str) -> None:
    if len(value) > 160 or _TYPED_ID.fullmatch(value) is None:
        raise LinkSessionRejectedError(reason_code)


def _secret_fingerprint(secret: bytes) -> bytes:
    return hashlib.sha256(secret).digest()


def _decode_salt(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise LinkSessionRejectedError("LINK_SESSION_SALT_INVALID") from error


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise LinkSessionRejectedError("LINK_SESSION_JSON_INVALID") from error


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LinkSessionRejectedError("LINK_SESSION_TIME_INVALID") from error
    _require_aware(parsed)
    return parsed


def _format_timestamp(value: datetime) -> str:
    _require_aware(value)
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise LinkSessionRejectedError("LINK_SESSION_TIMEZONE_REQUIRED")

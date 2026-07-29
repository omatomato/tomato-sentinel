"""End-to-end sealing for opaque Tomato Link payloads.

The relay routes the resulting bytes without access to the session key. Key
provisioning and durable key storage deliberately remain outside this module.
"""

import base64
import binascii
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

MAXIMUM_SEALED_PLAINTEXT_BYTES = 30_000
AES_GCM_KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 12
AES_GCM_TAG_BYTES = 16
MAXIMUM_TRACKED_NONCES = 1_024


class TomatoLinkSealRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class TomatoLinkBinding:
    frame_id: str
    organization_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    session_id: str
    sequence: int
    created_at: str
    expires_at: str

    def associated_data(self) -> bytes:
        return _canonical_json(
            {
                "binding_version": 1,
                "created_at": self.created_at,
                "destination_endpoint_id": self.destination_endpoint_id,
                "expires_at": self.expires_at,
                "frame_id": self.frame_id,
                "organization_id": self.organization_id,
                "sequence": self.sequence,
                "session_id": self.session_id,
                "source_endpoint_id": self.source_endpoint_id,
            }
        )


class TomatoLinkSealingBinding(Protocol):
    @property
    def organization_id(self) -> str: ...

    @property
    def source_endpoint_id(self) -> str: ...

    @property
    def destination_endpoint_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    def associated_data(self) -> bytes: ...


@dataclass(frozen=True, slots=True)
class TomatoLinkControlBinding:
    control_id: str
    organization_id: str
    source_endpoint_id: str
    destination_endpoint_id: str
    session_id: str
    sequence: int
    control_type: str
    job_id: str
    created_at: str
    expires_at: str

    def associated_data(self) -> bytes:
        return _canonical_json(
            {
                "binding_version": 2,
                "control_id": self.control_id,
                "control_type": self.control_type,
                "created_at": self.created_at,
                "destination_endpoint_id": self.destination_endpoint_id,
                "expires_at": self.expires_at,
                "job_id": self.job_id,
                "organization_id": self.organization_id,
                "sequence": self.sequence,
                "session_id": self.session_id,
                "source_endpoint_id": self.source_endpoint_id,
            }
        )


class TomatoLinkSessionKey:
    """A session-bound key that cannot reveal its bytes through repr."""

    __slots__ = (
        "_key",
        "destination_endpoint_id",
        "key_id",
        "organization_id",
        "session_id",
        "source_endpoint_id",
    )

    def __init__(
        self,
        *,
        key_id: str,
        organization_id: str,
        source_endpoint_id: str,
        session_id: str,
        destination_endpoint_id: str,
        key: bytes,
    ) -> None:
        if len(key) != AES_GCM_KEY_BYTES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_KEY_LENGTH_INVALID")
        self.key_id = key_id
        self.organization_id = organization_id
        self.source_endpoint_id = source_endpoint_id
        self.session_id = session_id
        self.destination_endpoint_id = destination_endpoint_id
        self._key = bytes(key)

    def __repr__(self) -> str:
        return (
            "TomatoLinkSessionKey("
            f"key_id={self.key_id!r}, "
            f"organization_id={self.organization_id!r}, "
            f"source_endpoint_id={self.source_endpoint_id!r}, "
            f"session_id={self.session_id!r}, "
            f"destination_endpoint_id={self.destination_endpoint_id!r}, "
            "key=<redacted>)"
        )

    def aead(self) -> AESGCM:
        return AESGCM(self._key)


class TomatoLinkSealedPayloadCodec:
    def __init__(
        self,
        schema: Mapping[str, Any],
        *,
        nonce_source: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)
        self._nonce_source = nonce_source
        self._used_nonces: set[tuple[str, bytes]] = set()

    def seal(
        self,
        plaintext: bytes,
        *,
        binding: TomatoLinkSealingBinding,
        session_key: TomatoLinkSessionKey,
    ) -> bytes:
        if not plaintext or len(plaintext) > MAXIMUM_SEALED_PLAINTEXT_BYTES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_PLAINTEXT_LENGTH_INVALID")
        _require_key_binding(binding, session_key)
        nonce = self._nonce_source(AES_GCM_NONCE_BYTES)
        if len(nonce) != AES_GCM_NONCE_BYTES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_NONCE_LENGTH_INVALID")
        nonce_key = (session_key.key_id, nonce)
        if nonce_key in self._used_nonces:
            raise TomatoLinkSealRejectedError("LINK_SEAL_NONCE_REUSED")
        if len(self._used_nonces) >= MAXIMUM_TRACKED_NONCES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_SESSION_EXHAUSTED")

        ciphertext = session_key.aead().encrypt(
            nonce,
            plaintext,
            binding.associated_data(),
        )
        self._used_nonces.add(nonce_key)
        envelope = {
            "algorithm": "AES-256-GCM",
            "ciphertext_base64": base64.b64encode(ciphertext).decode("ascii"),
            "contract_version": 1,
            "key_id": session_key.key_id,
            "nonce_base64": base64.b64encode(nonce).decode("ascii"),
            "plaintext_length": len(plaintext),
            "seal_version": 1,
        }
        try:
            self._validator.validate(envelope)
        except ValidationError as error:
            raise TomatoLinkSealRejectedError("LINK_SEAL_SCHEMA_INVALID") from error
        return _canonical_json(envelope)

    def open(
        self,
        sealed_payload: bytes,
        *,
        binding: TomatoLinkSealingBinding,
        session_key: TomatoLinkSessionKey,
    ) -> bytes:
        _require_key_binding(binding, session_key)
        try:
            value = json.loads(sealed_payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TomatoLinkSealRejectedError("LINK_SEAL_JSON_INVALID") from error
        if not isinstance(value, dict):
            raise TomatoLinkSealRejectedError("LINK_SEAL_JSON_INVALID")
        try:
            self._validator.validate(value)
        except ValidationError as error:
            raise TomatoLinkSealRejectedError("LINK_SEAL_SCHEMA_INVALID") from error
        if value["key_id"] != session_key.key_id:
            raise TomatoLinkSealRejectedError("LINK_SEAL_KEY_MISMATCH")

        nonce = _decode_base64(cast(str, value["nonce_base64"]))
        ciphertext = _decode_base64(cast(str, value["ciphertext_base64"]))
        if len(nonce) != AES_GCM_NONCE_BYTES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_NONCE_LENGTH_INVALID")
        plaintext_length = cast(int, value["plaintext_length"])
        if len(ciphertext) != plaintext_length + AES_GCM_TAG_BYTES:
            raise TomatoLinkSealRejectedError("LINK_SEAL_CIPHERTEXT_LENGTH_INVALID")
        try:
            plaintext = session_key.aead().decrypt(
                nonce,
                ciphertext,
                binding.associated_data(),
            )
        except InvalidTag as error:
            raise TomatoLinkSealRejectedError(
                "LINK_SEAL_AUTHENTICATION_INVALID"
            ) from error
        if len(plaintext) != plaintext_length:
            raise TomatoLinkSealRejectedError("LINK_SEAL_PLAINTEXT_LENGTH_INVALID")
        return plaintext


def binding_from_frame(frame: Mapping[str, object]) -> TomatoLinkBinding:
    try:
        return TomatoLinkBinding(
            frame_id=cast(str, frame["frame_id"]),
            organization_id=cast(str, frame["organization_id"]),
            source_endpoint_id=cast(str, frame["source_endpoint_id"]),
            destination_endpoint_id=cast(str, frame["destination_endpoint_id"]),
            session_id=cast(str, frame["session_id"]),
            sequence=cast(int, frame["sequence"]),
            created_at=cast(str, frame["created_at"]),
            expires_at=cast(str, frame["expires_at"]),
        )
    except KeyError as error:
        raise TomatoLinkSealRejectedError("LINK_SEAL_BINDING_INVALID") from error


def binding_from_control_frame(
    frame: Mapping[str, object],
) -> TomatoLinkControlBinding:
    try:
        return TomatoLinkControlBinding(
            control_id=cast(str, frame["control_id"]),
            organization_id=cast(str, frame["organization_id"]),
            source_endpoint_id=cast(str, frame["source_endpoint_id"]),
            destination_endpoint_id=cast(str, frame["destination_endpoint_id"]),
            session_id=cast(str, frame["session_id"]),
            sequence=cast(int, frame["sequence"]),
            control_type=cast(str, frame["control_type"]),
            job_id=cast(str, frame["job_id"]),
            created_at=cast(str, frame["created_at"]),
            expires_at=cast(str, frame["expires_at"]),
        )
    except KeyError as error:
        raise TomatoLinkSealRejectedError("LINK_SEAL_BINDING_INVALID") from error


def _require_key_binding(
    binding: TomatoLinkSealingBinding,
    session_key: TomatoLinkSessionKey,
) -> None:
    if (
        binding.organization_id != session_key.organization_id
        or binding.source_endpoint_id != session_key.source_endpoint_id
        or binding.session_id != session_key.session_id
        or binding.destination_endpoint_id != session_key.destination_endpoint_id
    ):
        raise TomatoLinkSealRejectedError("LINK_SEAL_KEY_BINDING_MISMATCH")


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise TomatoLinkSealRejectedError("LINK_SEAL_BASE64_INVALID") from error


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
        raise TomatoLinkSealRejectedError("LINK_SEAL_JSON_INVALID") from error

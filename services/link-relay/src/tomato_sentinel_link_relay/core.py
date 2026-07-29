"""Bounded, provider-neutral Tomato Link relay core.

This module deliberately opens no listener and provides no confidentiality.
It models the routing and isolation boundary that a future authenticated
WebSocket adapter must call.
"""

import base64
import binascii
import hashlib
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

MAXIMUM_FRAME_BYTES = 65_536
MAXIMUM_OPAQUE_PAYLOAD_BYTES = 32_768
MAXIMUM_FRAME_TTL = timedelta(seconds=120)
MAXIMUM_CLOCK_SKEW = timedelta(seconds=30)
MAXIMUM_QUEUED_FRAMES_PER_ENDPOINT = 64
MAXIMUM_QUEUED_BYTES_PER_ENDPOINT = 262_144
MAXIMUM_PULL_FRAMES = 16
MAXIMUM_RECEIPT_RECORDS = 1_024


class TomatoLinkRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class RelayEndpointRole(StrEnum):
    DEVICE = "device"
    EDGE = "edge"


@dataclass(frozen=True, slots=True)
class RelayEndpoint:
    endpoint_id: str
    organization_id: str
    role: RelayEndpointRole
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AuthenticatedRelayPeer:
    endpoint_id: str
    organization_id: str
    role: RelayEndpointRole
    authenticated: bool


@dataclass(frozen=True, slots=True)
class RelayReceipt:
    frame_id: str
    state: str
    destination_endpoint_id: str
    execution_mode: str = "simulation"


@dataclass(frozen=True, slots=True)
class QueuedFrame:
    frame_id: str
    payload: Mapping[str, object]
    payload_length: int
    expires_at: datetime


class TomatoLinkFrameValidator:
    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    def validate(
        self,
        frame: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> tuple[bytes, datetime]:
        _require_aware(received_at)
        encoded = _canonical_json(frame)
        if len(encoded) > MAXIMUM_FRAME_BYTES:
            raise TomatoLinkRejectedError("LINK_FRAME_TOO_LARGE")
        try:
            self._validator.validate(frame)
        except ValidationError as error:
            raise TomatoLinkRejectedError("LINK_FRAME_SCHEMA_INVALID") from error

        try:
            payload = base64.b64decode(
                cast(str, frame["opaque_payload"]),
                validate=True,
            )
        except (binascii.Error, ValueError) as error:
            raise TomatoLinkRejectedError("LINK_PAYLOAD_BASE64_INVALID") from error
        if (
            len(payload) != frame["payload_length"]
            or len(payload) > MAXIMUM_OPAQUE_PAYLOAD_BYTES
        ):
            raise TomatoLinkRejectedError("LINK_PAYLOAD_LENGTH_INVALID")
        expected_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if frame["payload_sha256"] != expected_digest:
            raise TomatoLinkRejectedError("LINK_PAYLOAD_DIGEST_INVALID")

        created_at = _timestamp(cast(str, frame["created_at"]))
        expires_at = _timestamp(cast(str, frame["expires_at"]))
        if (
            expires_at <= created_at
            or expires_at - created_at > MAXIMUM_FRAME_TTL
            or created_at > received_at + MAXIMUM_CLOCK_SKEW
            or received_at >= expires_at
        ):
            raise TomatoLinkRejectedError("LINK_FRAME_TIME_INVALID")
        return payload, expires_at


class InMemoryTomatoLinkRelay:
    """Authenticated routing core with bounded in-memory queues."""

    def __init__(
        self,
        validator: TomatoLinkFrameValidator,
        endpoints: tuple[RelayEndpoint, ...],
    ) -> None:
        self._validator = validator
        self._endpoints: dict[str, RelayEndpoint] = {}
        for endpoint in endpoints:
            if endpoint.endpoint_id in self._endpoints:
                raise TomatoLinkRejectedError("LINK_ENDPOINT_DUPLICATE")
            self._endpoints[endpoint.endpoint_id] = endpoint
        self._queues: dict[str, deque[QueuedFrame]] = {}
        self._queued_bytes: dict[str, int] = {}
        self._receipts: dict[tuple[str, str], tuple[str, RelayReceipt]] = {}
        self._receipt_order: deque[tuple[str, str]] = deque()
        self._last_sequences: dict[tuple[str, str], int] = {}

    def publish(
        self,
        frame: Mapping[str, object],
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
    ) -> RelayReceipt:
        source = self._require_peer(peer)
        payload, expires_at = self._validator.validate(
            frame,
            received_at=received_at,
        )
        fingerprint = hashlib.sha256(_canonical_json(frame)).hexdigest()
        frame_id = cast(str, frame["frame_id"])
        destination_id = cast(str, frame["destination_endpoint_id"])
        destination = self._endpoints.get(destination_id)
        if (
            frame["source_endpoint_id"] != source.endpoint_id
            or frame["organization_id"] != source.organization_id
        ):
            raise TomatoLinkRejectedError("LINK_SOURCE_BINDING_MISMATCH")
        if destination is None or not destination.enabled:
            raise TomatoLinkRejectedError("LINK_DESTINATION_UNAVAILABLE")
        if destination.organization_id != source.organization_id:
            raise TomatoLinkRejectedError("LINK_CROSS_ORGANIZATION_DENIED")
        if destination.role is source.role:
            raise TomatoLinkRejectedError("LINK_ROUTE_ROLE_DENIED")

        receipt_key = (source.organization_id, frame_id)
        existing = self._receipts.get(receipt_key)
        if existing is not None:
            if existing[0] != fingerprint:
                raise TomatoLinkRejectedError("LINK_FRAME_ID_REUSED")
            return existing[1]

        session_id = cast(str, frame["session_id"])
        sequence = cast(int, frame["sequence"])
        sequence_key = (source.endpoint_id, session_id)
        if sequence <= self._last_sequences.get(sequence_key, 0):
            raise TomatoLinkRejectedError("LINK_SEQUENCE_REPLAYED")

        queue = self._queues.setdefault(destination_id, deque())
        queued_bytes = self._queued_bytes.get(destination_id, 0)
        if len(queue) >= MAXIMUM_QUEUED_FRAMES_PER_ENDPOINT:
            raise TomatoLinkRejectedError("LINK_DESTINATION_QUEUE_FULL")
        if queued_bytes + len(payload) > MAXIMUM_QUEUED_BYTES_PER_ENDPOINT:
            raise TomatoLinkRejectedError("LINK_DESTINATION_BYTES_FULL")

        queue.append(
            QueuedFrame(
                frame_id=frame_id,
                payload=dict(frame),
                payload_length=len(payload),
                expires_at=expires_at,
            )
        )
        self._queued_bytes[destination_id] = queued_bytes + len(payload)
        self._last_sequences[sequence_key] = sequence
        receipt = RelayReceipt(
            frame_id=frame_id,
            state="queued",
            destination_endpoint_id=destination_id,
        )
        self._remember_receipt(receipt_key, fingerprint, receipt)
        return receipt

    def pull(
        self,
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]:
        endpoint = self._require_peer(peer)
        _require_aware(received_at)
        if isinstance(limit, bool) or not 1 <= limit <= MAXIMUM_PULL_FRAMES:
            raise TomatoLinkRejectedError("LINK_PULL_LIMIT_INVALID")
        queue = self._queues.setdefault(endpoint.endpoint_id, deque())
        self._discard_expired(queue, endpoint.endpoint_id, received_at)
        return tuple(dict(item.payload) for item in tuple(queue)[:limit])

    def acknowledge(
        self,
        frame_id: str,
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
    ) -> RelayReceipt:
        endpoint = self._require_peer(peer)
        _require_aware(received_at)
        queue = self._queues.setdefault(endpoint.endpoint_id, deque())
        self._discard_expired(queue, endpoint.endpoint_id, received_at)
        for item in queue:
            if item.frame_id != frame_id:
                continue
            queue.remove(item)
            self._queued_bytes[endpoint.endpoint_id] -= item.payload_length
            receipt = RelayReceipt(
                frame_id=frame_id,
                state="acknowledged",
                destination_endpoint_id=endpoint.endpoint_id,
            )
            receipt_key = (endpoint.organization_id, frame_id)
            previous = self._receipts.get(receipt_key)
            if previous is not None:
                self._receipts[receipt_key] = (previous[0], receipt)
            return receipt
        raise TomatoLinkRejectedError("LINK_FRAME_NOT_QUEUED_FOR_PEER")

    def _require_peer(self, peer: AuthenticatedRelayPeer) -> RelayEndpoint:
        if not peer.authenticated:
            raise TomatoLinkRejectedError("LINK_PEER_UNAUTHENTICATED")
        endpoint = self._endpoints.get(peer.endpoint_id)
        if endpoint is None or not endpoint.enabled:
            raise TomatoLinkRejectedError("LINK_ENDPOINT_UNAVAILABLE")
        if (
            peer.organization_id != endpoint.organization_id
            or peer.role is not endpoint.role
        ):
            raise TomatoLinkRejectedError("LINK_PEER_BINDING_MISMATCH")
        return endpoint

    def _discard_expired(
        self,
        queue: deque[QueuedFrame],
        endpoint_id: str,
        received_at: datetime,
    ) -> None:
        retained = deque(item for item in queue if received_at < item.expires_at)
        if len(retained) == len(queue):
            return
        queue.clear()
        queue.extend(retained)
        self._queued_bytes[endpoint_id] = sum(item.payload_length for item in retained)

    def _remember_receipt(
        self,
        receipt_key: tuple[str, str],
        fingerprint: str,
        receipt: RelayReceipt,
    ) -> None:
        if len(self._receipt_order) >= MAXIMUM_RECEIPT_RECORDS:
            expired_key = self._receipt_order.popleft()
            self._receipts.pop(expired_key, None)
        self._receipt_order.append(receipt_key)
        self._receipts[receipt_key] = (fingerprint, receipt)


def build_opaque_frame(
    *,
    frame_id: str,
    organization_id: str,
    source_endpoint_id: str,
    destination_endpoint_id: str,
    session_id: str,
    sequence: int,
    created_at: datetime,
    expires_at: datetime,
    payload: bytes,
) -> dict[str, object]:
    """Build a simulation frame without claiming transport encryption."""

    _require_aware(created_at)
    _require_aware(expires_at)
    if not payload or len(payload) > MAXIMUM_OPAQUE_PAYLOAD_BYTES:
        raise TomatoLinkRejectedError("LINK_PAYLOAD_LENGTH_INVALID")
    return {
        "contract_version": 1,
        "link_version": 1,
        "frame_id": frame_id,
        "organization_id": organization_id,
        "source_endpoint_id": source_endpoint_id,
        "destination_endpoint_id": destination_endpoint_id,
        "session_id": session_id,
        "sequence": sequence,
        "created_at": _format_timestamp(created_at),
        "expires_at": _format_timestamp(expires_at),
        "payload_encoding": "opaque_base64",
        "payload_length": len(payload),
        "payload_sha256": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        "opaque_payload": base64.b64encode(payload).decode("ascii"),
        "execution_mode": "simulation",
    }


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
        raise TomatoLinkRejectedError("LINK_FRAME_NOT_JSON") from error


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TomatoLinkRejectedError("LINK_FRAME_TIME_INVALID") from error
    _require_aware(parsed)
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise TomatoLinkRejectedError("LINK_TIMEZONE_REQUIRED")

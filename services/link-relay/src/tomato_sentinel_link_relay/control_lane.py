"""Independent bounded relay lane for authenticated physical cancellation."""

import base64
import binascii
import hashlib
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .core import AuthenticatedRelayPeer, RelayEndpoint, RelayEndpointRole

MAXIMUM_CONTROL_FRAME_BYTES = 8_192
MAXIMUM_CONTROL_PAYLOAD_BYTES = 2_048
MAXIMUM_CONTROL_TTL = timedelta(seconds=30)
MAXIMUM_CONTROL_CLOCK_SKEW = timedelta(seconds=30)
MAXIMUM_CONTROL_QUEUE_FRAMES = 16
MAXIMUM_CONTROL_QUEUE_BYTES = 32_768
MAXIMUM_CONTROL_PULL = 8
MAXIMUM_CONTROL_RECEIPTS = 512


class TomatoLinkControlRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ControlReceipt:
    control_id: str
    state: str
    destination_endpoint_id: str
    execution_mode: str = "simulation"


@dataclass(frozen=True, slots=True)
class _QueuedControl:
    control_id: str
    frame: Mapping[str, object]
    payload_length: int
    expires_at: datetime


class TomatoLinkCancelFrameValidator:
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
        if len(_canonical_json(frame)) > MAXIMUM_CONTROL_FRAME_BYTES:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_FRAME_TOO_LARGE")
        try:
            self._validator.validate(frame)
        except ValidationError as error:
            raise TomatoLinkControlRejectedError(
                "LINK_CONTROL_SCHEMA_INVALID"
            ) from error
        try:
            payload = base64.b64decode(
                cast(str, frame["opaque_payload"]),
                validate=True,
            )
        except (binascii.Error, ValueError) as error:
            raise TomatoLinkControlRejectedError(
                "LINK_CONTROL_BASE64_INVALID"
            ) from error
        if (
            len(payload) != frame["payload_length"]
            or len(payload) > MAXIMUM_CONTROL_PAYLOAD_BYTES
        ):
            raise TomatoLinkControlRejectedError("LINK_CONTROL_LENGTH_INVALID")
        expected_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if frame["payload_sha256"] != expected_digest:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_DIGEST_INVALID")
        created_at = _timestamp(cast(str, frame["created_at"]))
        expires_at = _timestamp(cast(str, frame["expires_at"]))
        if (
            expires_at <= created_at
            or expires_at - created_at > MAXIMUM_CONTROL_TTL
            or created_at > received_at + MAXIMUM_CONTROL_CLOCK_SKEW
            or received_at >= expires_at
        ):
            raise TomatoLinkControlRejectedError("LINK_CONTROL_TIME_INVALID")
        return payload, expires_at


class InMemoryTomatoLinkControlLane:
    """A separate queue so ordinary frames cannot starve cancellation."""

    def __init__(
        self,
        validator: TomatoLinkCancelFrameValidator,
        endpoints: tuple[RelayEndpoint, ...],
    ) -> None:
        self._validator = validator
        self._endpoints: dict[str, RelayEndpoint] = {}
        for endpoint in endpoints:
            if endpoint.endpoint_id in self._endpoints:
                raise TomatoLinkControlRejectedError("LINK_ENDPOINT_DUPLICATE")
            self._endpoints[endpoint.endpoint_id] = endpoint
        self._queues: dict[str, deque[_QueuedControl]] = {}
        self._queued_bytes: dict[str, int] = {}
        self._receipts: dict[tuple[str, str], tuple[str, ControlReceipt]] = {}
        self._receipt_order: deque[tuple[str, str]] = deque()
        self._last_sequences: dict[tuple[str, str], int] = {}

    def publish(
        self,
        frame: Mapping[str, object],
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
    ) -> ControlReceipt:
        source = self._require_peer(peer)
        if source.role is not RelayEndpointRole.DEVICE:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_SOURCE_ROLE_DENIED")
        payload, expires_at = self._validator.validate(
            frame,
            received_at=received_at,
        )
        if (
            frame["source_endpoint_id"] != source.endpoint_id
            or frame["organization_id"] != source.organization_id
        ):
            raise TomatoLinkControlRejectedError("LINK_CONTROL_SOURCE_BINDING_MISMATCH")
        destination_id = cast(str, frame["destination_endpoint_id"])
        destination = self._endpoints.get(destination_id)
        if destination is None or not destination.enabled:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_DESTINATION_UNAVAILABLE")
        if destination.organization_id != source.organization_id:
            raise TomatoLinkControlRejectedError(
                "LINK_CONTROL_CROSS_ORGANIZATION_DENIED"
            )
        if destination.role is not RelayEndpointRole.EDGE:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_DESTINATION_ROLE_DENIED")

        control_id = cast(str, frame["control_id"])
        fingerprint = hashlib.sha256(_canonical_json(frame)).hexdigest()
        receipt_key = (source.organization_id, control_id)
        existing = self._receipts.get(receipt_key)
        if existing is not None:
            if existing[0] != fingerprint:
                raise TomatoLinkControlRejectedError("LINK_CONTROL_ID_REUSED")
            return existing[1]

        session_id = cast(str, frame["session_id"])
        sequence = cast(int, frame["sequence"])
        sequence_key = (source.endpoint_id, session_id)
        if sequence <= self._last_sequences.get(sequence_key, 0):
            raise TomatoLinkControlRejectedError("LINK_CONTROL_SEQUENCE_REPLAYED")
        queue = self._queues.setdefault(destination_id, deque())
        queued_bytes = self._queued_bytes.get(destination_id, 0)
        if len(queue) >= MAXIMUM_CONTROL_QUEUE_FRAMES:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_QUEUE_FULL")
        if queued_bytes + len(payload) > MAXIMUM_CONTROL_QUEUE_BYTES:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_BYTES_FULL")

        queue.append(
            _QueuedControl(
                control_id=control_id,
                frame=dict(frame),
                payload_length=len(payload),
                expires_at=expires_at,
            )
        )
        self._queued_bytes[destination_id] = queued_bytes + len(payload)
        self._last_sequences[sequence_key] = sequence
        receipt = ControlReceipt(
            control_id=control_id,
            state="queued",
            destination_endpoint_id=destination_id,
        )
        self._remember(receipt_key, fingerprint, receipt)
        return receipt

    def pull(
        self,
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]:
        endpoint = self._require_peer(peer)
        if endpoint.role is not RelayEndpointRole.EDGE:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_PULL_ROLE_DENIED")
        _require_aware(received_at)
        if isinstance(limit, bool) or not 1 <= limit <= MAXIMUM_CONTROL_PULL:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_PULL_LIMIT_INVALID")
        queue = self._queues.setdefault(endpoint.endpoint_id, deque())
        self._discard_expired(queue, endpoint.endpoint_id, received_at)
        return tuple(dict(item.frame) for item in tuple(queue)[:limit])

    def acknowledge(
        self,
        control_id: str,
        *,
        peer: AuthenticatedRelayPeer,
        received_at: datetime,
    ) -> ControlReceipt:
        endpoint = self._require_peer(peer)
        if endpoint.role is not RelayEndpointRole.EDGE:
            raise TomatoLinkControlRejectedError("LINK_CONTROL_ACK_ROLE_DENIED")
        _require_aware(received_at)
        queue = self._queues.setdefault(endpoint.endpoint_id, deque())
        self._discard_expired(queue, endpoint.endpoint_id, received_at)
        for item in queue:
            if item.control_id != control_id:
                continue
            queue.remove(item)
            self._queued_bytes[endpoint.endpoint_id] -= item.payload_length
            receipt = ControlReceipt(
                control_id=control_id,
                state="acknowledged",
                destination_endpoint_id=endpoint.endpoint_id,
            )
            receipt_key = (endpoint.organization_id, control_id)
            previous = self._receipts.get(receipt_key)
            if previous is not None:
                self._receipts[receipt_key] = (previous[0], receipt)
            return receipt
        raise TomatoLinkControlRejectedError("LINK_CONTROL_NOT_QUEUED_FOR_PEER")

    def _require_peer(self, peer: AuthenticatedRelayPeer) -> RelayEndpoint:
        if not peer.authenticated:
            raise TomatoLinkControlRejectedError("LINK_PEER_UNAUTHENTICATED")
        endpoint = self._endpoints.get(peer.endpoint_id)
        if endpoint is None or not endpoint.enabled:
            raise TomatoLinkControlRejectedError("LINK_ENDPOINT_UNAVAILABLE")
        if (
            peer.organization_id != endpoint.organization_id
            or peer.role is not endpoint.role
        ):
            raise TomatoLinkControlRejectedError("LINK_PEER_BINDING_MISMATCH")
        return endpoint

    def _discard_expired(
        self,
        queue: deque[_QueuedControl],
        endpoint_id: str,
        received_at: datetime,
    ) -> None:
        retained = deque(item for item in queue if received_at < item.expires_at)
        if len(retained) == len(queue):
            return
        queue.clear()
        queue.extend(retained)
        self._queued_bytes[endpoint_id] = sum(item.payload_length for item in retained)

    def _remember(
        self,
        receipt_key: tuple[str, str],
        fingerprint: str,
        receipt: ControlReceipt,
    ) -> None:
        if len(self._receipt_order) >= MAXIMUM_CONTROL_RECEIPTS:
            expired = self._receipt_order.popleft()
            self._receipts.pop(expired, None)
        self._receipt_order.append(receipt_key)
        self._receipts[receipt_key] = (fingerprint, receipt)


def build_cancel_frame(
    *,
    control_id: str,
    organization_id: str,
    source_endpoint_id: str,
    destination_endpoint_id: str,
    session_id: str,
    sequence: int,
    job_id: str,
    created_at: datetime,
    expires_at: datetime,
    sealed_payload: bytes,
) -> dict[str, object]:
    _require_aware(created_at)
    _require_aware(expires_at)
    if not sealed_payload or len(sealed_payload) > MAXIMUM_CONTROL_PAYLOAD_BYTES:
        raise TomatoLinkControlRejectedError("LINK_CONTROL_LENGTH_INVALID")
    return {
        "contract_version": 1,
        "control_version": 1,
        "control_id": control_id,
        "organization_id": organization_id,
        "source_endpoint_id": source_endpoint_id,
        "destination_endpoint_id": destination_endpoint_id,
        "session_id": session_id,
        "sequence": sequence,
        "control_type": "physical_cancel",
        "job_id": job_id,
        "created_at": _format_timestamp(created_at),
        "expires_at": _format_timestamp(expires_at),
        "payload_encoding": "sealed_json_base64",
        "payload_length": len(sealed_payload),
        "payload_sha256": f"sha256:{hashlib.sha256(sealed_payload).hexdigest()}",
        "opaque_payload": base64.b64encode(sealed_payload).decode("ascii"),
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
        raise TomatoLinkControlRejectedError("LINK_CONTROL_JSON_INVALID") from error


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TomatoLinkControlRejectedError("LINK_CONTROL_TIME_INVALID") from error
    _require_aware(parsed)
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise TomatoLinkControlRejectedError("LINK_CONTROL_TIMEZONE_REQUIRED")

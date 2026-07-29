import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from tomato_sentinel_link_relay import (
    AuthenticatedRelayPeer,
    InMemoryTomatoLinkControlLane,
    InMemoryTomatoLinkRelay,
    RelayEndpoint,
    RelayEndpointRole,
    TomatoLinkCancelFrameValidator,
    TomatoLinkControlBinding,
    TomatoLinkControlRejectedError,
    TomatoLinkFrameValidator,
    TomatoLinkSealedPayloadCodec,
    TomatoLinkSealRejectedError,
    TomatoLinkSessionKey,
    binding_from_control_frame,
    build_cancel_frame,
    build_opaque_frame,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
NOW = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)
ENDPOINTS = (
    RelayEndpoint(
        endpoint_id="cardputer:01",
        organization_id="organization:01",
        role=RelayEndpointRole.DEVICE,
    ),
    RelayEndpoint(
        endpoint_id="edge:home-01",
        organization_id="organization:01",
        role=RelayEndpointRole.EDGE,
    ),
    RelayEndpoint(
        endpoint_id="edge:other-01",
        organization_id="organization:02",
        role=RelayEndpointRole.EDGE,
    ),
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def device_peer() -> AuthenticatedRelayPeer:
    return AuthenticatedRelayPeer(
        endpoint_id="cardputer:01",
        organization_id="organization:01",
        role=RelayEndpointRole.DEVICE,
        authenticated=True,
    )


def edge_peer() -> AuthenticatedRelayPeer:
    return AuthenticatedRelayPeer(
        endpoint_id="edge:home-01",
        organization_id="organization:01",
        role=RelayEndpointRole.EDGE,
        authenticated=True,
    )


def session_key() -> TomatoLinkSessionKey:
    return TomatoLinkSessionKey(
        key_id="link-root-key:01",
        organization_id="organization:01",
        source_endpoint_id="cardputer:01",
        destination_endpoint_id="edge:home-01",
        session_id="link-session:01",
        key=bytes(range(32)),
    )


def codec() -> TomatoLinkSealedPayloadCodec:
    return TomatoLinkSealedPayloadCodec(
        load_json(SCHEMAS / "tomato-link-sealed-payload.schema.json"),
        nonce_source=lambda _: b"\x31" * 12,
    )


def binding(
    *,
    control_id: str = "link-control:01",
    sequence: int = 1,
    job_id: str = "job:camera-monitor-01",
) -> TomatoLinkControlBinding:
    return TomatoLinkControlBinding(
        control_id=control_id,
        organization_id="organization:01",
        source_endpoint_id="cardputer:01",
        destination_endpoint_id="edge:home-01",
        session_id="link-session:01",
        sequence=sequence,
        control_type="physical_cancel",
        job_id=job_id,
        created_at="2026-07-29T09:00:00Z",
        expires_at="2026-07-29T09:00:20Z",
    )


def cancellation_payload(job_id: str = "job:camera-monitor-01") -> bytes:
    return json.dumps(
        {
            "contract_version": 1,
            "job_id": job_id,
            "input_source": "physical_cancel_key",
            "requested_at": "2026-07-29T09:00:00Z",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def frame(
    *,
    control_id: str = "link-control:01",
    sequence: int = 1,
    job_id: str = "job:camera-monitor-01",
) -> dict[str, object]:
    control_binding = binding(
        control_id=control_id,
        sequence=sequence,
        job_id=job_id,
    )
    sealed = codec().seal(
        cancellation_payload(job_id),
        binding=control_binding,
        session_key=session_key(),
    )
    return build_cancel_frame(
        control_id=control_id,
        organization_id="organization:01",
        source_endpoint_id="cardputer:01",
        destination_endpoint_id="edge:home-01",
        session_id="link-session:01",
        sequence=sequence,
        job_id=job_id,
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=20),
        sealed_payload=sealed,
    )


def lane() -> InMemoryTomatoLinkControlLane:
    return InMemoryTomatoLinkControlLane(
        TomatoLinkCancelFrameValidator(
            load_json(SCHEMAS / "tomato-link-cancel-frame.schema.json")
        ),
        ENDPOINTS,
    )


def test_physical_cancel_is_sealed_delivered_and_acknowledged() -> None:
    control_lane = lane()
    message = frame()

    queued = control_lane.publish(message, peer=device_peer(), received_at=NOW)
    received = control_lane.pull(peer=edge_peer(), received_at=NOW, limit=1)[0]
    sealed = base64.b64decode(cast(str, received["opaque_payload"]))
    opened = codec().open(
        sealed,
        binding=binding_from_control_frame(received),
        session_key=session_key(),
    )
    payload = json.loads(opened)
    acknowledged = control_lane.acknowledge(
        "link-control:01",
        peer=edge_peer(),
        received_at=NOW,
    )

    assert queued.state == "queued"
    assert payload["input_source"] == "physical_cancel_key"
    assert payload["job_id"] == received["job_id"]
    assert acknowledged.state == "acknowledged"


def test_outer_job_tampering_cannot_redirect_sealed_cancellation() -> None:
    message = frame()
    message["job_id"] = "job:different"
    control_lane = lane()
    control_lane.publish(message, peer=device_peer(), received_at=NOW)
    received = control_lane.pull(peer=edge_peer(), received_at=NOW, limit=1)[0]

    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        codec().open(
            base64.b64decode(cast(str, received["opaque_payload"])),
            binding=binding_from_control_frame(received),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == "LINK_SEAL_AUTHENTICATION_INVALID"


def test_control_lane_remains_available_when_ordinary_queue_is_full() -> None:
    ordinary = InMemoryTomatoLinkRelay(
        TomatoLinkFrameValidator(load_json(SCHEMAS / "tomato-link-frame.schema.json")),
        ENDPOINTS,
    )
    for sequence in range(1, 65):
        ordinary.publish(
            build_opaque_frame(
                frame_id=f"link-frame:{sequence:03d}",
                organization_id="organization:01",
                source_endpoint_id="cardputer:01",
                destination_endpoint_id="edge:home-01",
                session_id="link-session:ordinary",
                sequence=sequence,
                created_at=NOW,
                expires_at=NOW + timedelta(seconds=60),
                payload=b"ordinary",
            ),
            peer=device_peer(),
            received_at=NOW,
        )
    control_lane = lane()

    receipt = control_lane.publish(frame(), peer=device_peer(), received_at=NOW)

    assert receipt.state == "queued"
    assert len(control_lane.pull(peer=edge_peer(), received_at=NOW, limit=1)) == 1


def test_exact_control_retry_is_idempotent_and_changed_id_reuse_is_denied() -> None:
    control_lane = lane()
    message = frame()
    first = control_lane.publish(message, peer=device_peer(), received_at=NOW)
    retry = control_lane.publish(message, peer=device_peer(), received_at=NOW)
    changed = frame()
    changed["job_id"] = "job:changed"

    with pytest.raises(TomatoLinkControlRejectedError) as rejected:
        control_lane.publish(changed, peer=device_peer(), received_at=NOW)

    assert retry == first
    assert rejected.value.reason_code == "LINK_CONTROL_ID_REUSED"


def test_edge_cannot_publish_into_device_only_control_lane() -> None:
    with pytest.raises(TomatoLinkControlRejectedError) as rejected:
        lane().publish(frame(), peer=edge_peer(), received_at=NOW)

    assert rejected.value.reason_code == "LINK_CONTROL_SOURCE_ROLE_DENIED"


@pytest.mark.parametrize(
    ("change", "reason_code"),
    [
        (
            {"organization_id": "organization:02"},
            "LINK_CONTROL_SOURCE_BINDING_MISMATCH",
        ),
        (
            {"destination_endpoint_id": "edge:other-01"},
            "LINK_CONTROL_CROSS_ORGANIZATION_DENIED",
        ),
        ({"expires_at": "2026-07-29T09:00:31Z"}, "LINK_CONTROL_TIME_INVALID"),
    ],
)
def test_control_scope_and_time_fail_closed(
    change: dict[str, object],
    reason_code: str,
) -> None:
    message = frame()
    message.update(change)

    with pytest.raises(TomatoLinkControlRejectedError) as rejected:
        lane().publish(message, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == reason_code

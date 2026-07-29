import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tomato_sentinel_link_relay import (
    MAXIMUM_OPAQUE_PAYLOAD_BYTES,
    MAXIMUM_QUEUED_FRAMES_PER_ENDPOINT,
    AuthenticatedRelayPeer,
    InMemoryTomatoLinkRelay,
    RelayEndpoint,
    RelayEndpointRole,
    TomatoLinkFrameValidator,
    TomatoLinkRejectedError,
    build_opaque_frame,
)

ROOT = Path(__file__).parents[3]
SCHEMA = (
    ROOT / "packages" / "contracts" / "schemas" / "v1" / "tomato-link-frame.schema.json"
)
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def load_schema() -> dict[str, Any]:
    with SCHEMA.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def device_peer(
    organization_id: str = "organization:01",
) -> AuthenticatedRelayPeer:
    return AuthenticatedRelayPeer(
        endpoint_id="cardputer:01",
        organization_id=organization_id,
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


def relay() -> InMemoryTomatoLinkRelay:
    return InMemoryTomatoLinkRelay(
        TomatoLinkFrameValidator(load_schema()),
        (
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
            RelayEndpoint(
                endpoint_id="cardputer:disabled",
                organization_id="organization:01",
                role=RelayEndpointRole.DEVICE,
                enabled=False,
            ),
        ),
    )


def frame(
    *,
    frame_id: str = "link-frame:01",
    sequence: int = 1,
    destination_endpoint_id: str = "edge:home-01",
    payload: bytes = b"signed-device-envelope",
    expires_at: datetime | None = None,
) -> dict[str, object]:
    return build_opaque_frame(
        frame_id=frame_id,
        organization_id="organization:01",
        source_endpoint_id="cardputer:01",
        destination_endpoint_id=destination_endpoint_id,
        session_id="link-session:01",
        sequence=sequence,
        created_at=NOW,
        expires_at=expires_at or NOW + timedelta(seconds=60),
        payload=payload,
    )


def test_authenticated_device_can_queue_and_edge_can_acknowledge_frame() -> None:
    link = relay()
    message = frame()

    receipt = link.publish(message, peer=device_peer(), received_at=NOW)
    delivered = link.pull(peer=edge_peer(), received_at=NOW, limit=1)
    acknowledged = link.acknowledge(
        "link-frame:01",
        peer=edge_peer(),
        received_at=NOW,
    )

    assert receipt.state == "queued"
    assert receipt.execution_mode == "simulation"
    assert delivered == (message,)
    assert acknowledged.state == "acknowledged"
    assert link.pull(peer=edge_peer(), received_at=NOW, limit=1) == ()


def test_exact_retransmission_is_idempotent_and_not_queued_twice() -> None:
    link = relay()
    message = frame()

    first = link.publish(message, peer=device_peer(), received_at=NOW)
    repeated = link.publish(message, peer=device_peer(), received_at=NOW)

    assert repeated == first
    assert len(link.pull(peer=edge_peer(), received_at=NOW, limit=16)) == 1


def test_retransmission_after_ack_reports_acknowledged_without_requeue() -> None:
    link = relay()
    message = frame()
    link.publish(message, peer=device_peer(), received_at=NOW)
    link.acknowledge("link-frame:01", peer=edge_peer(), received_at=NOW)

    repeated = link.publish(message, peer=device_peer(), received_at=NOW)

    assert repeated.state == "acknowledged"
    assert link.pull(peer=edge_peer(), received_at=NOW, limit=1) == ()


def test_modified_frame_id_is_rejected_without_advancing_sequence() -> None:
    link = relay()
    link.publish(frame(), peer=device_peer(), received_at=NOW)
    modified = frame(payload=b"different")

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        link.publish(modified, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == "LINK_FRAME_ID_REUSED"


def test_unauthenticated_peer_is_denied_before_frame_processing() -> None:
    peer = device_peer()
    unauthenticated = AuthenticatedRelayPeer(
        endpoint_id=peer.endpoint_id,
        organization_id=peer.organization_id,
        role=peer.role,
        authenticated=False,
    )
    malformed = {"not": "a frame"}

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(malformed, peer=unauthenticated, received_at=NOW)

    assert rejected.value.reason_code == "LINK_PEER_UNAUTHENTICATED"


def test_source_binding_mismatch_is_denied() -> None:
    message = frame()
    message["source_endpoint_id"] = "cardputer:forged"

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(message, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == "LINK_SOURCE_BINDING_MISMATCH"


def test_cross_organization_destination_is_denied() -> None:
    message = frame(destination_endpoint_id="edge:other-01")

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(message, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == "LINK_CROSS_ORGANIZATION_DENIED"


def test_same_role_route_is_denied() -> None:
    message = frame(destination_endpoint_id="cardputer:disabled")
    message["destination_endpoint_id"] = "cardputer:01"

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(message, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == "LINK_ROUTE_ROLE_DENIED"


def test_forged_peer_organization_is_denied() -> None:
    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(
            frame(),
            peer=device_peer("organization:02"),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "LINK_PEER_BINDING_MISMATCH"


def test_non_increasing_sequence_is_rejected() -> None:
    link = relay()
    link.publish(frame(), peer=device_peer(), received_at=NOW)

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        link.publish(
            frame(frame_id="link-frame:02"),
            peer=device_peer(),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "LINK_SEQUENCE_REPLAYED"


@pytest.mark.parametrize(
    ("change", "reason_code"),
    [
        ({"opaque_payload": "not base64"}, "LINK_PAYLOAD_BASE64_INVALID"),
        ({"payload_length": 1}, "LINK_PAYLOAD_LENGTH_INVALID"),
        ({"payload_sha256": "sha256:" + "0" * 64}, "LINK_PAYLOAD_DIGEST_INVALID"),
    ],
)
def test_corrupt_payload_is_rejected(
    change: dict[str, object],
    reason_code: str,
) -> None:
    message = frame()
    message.update(change)

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(message, peer=device_peer(), received_at=NOW)

    assert rejected.value.reason_code == reason_code


@pytest.mark.parametrize(
    "expires_at",
    [
        NOW,
        NOW + timedelta(seconds=121),
    ],
)
def test_invalid_or_unbounded_expiry_is_rejected(expires_at: datetime) -> None:
    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().publish(
            frame(expires_at=expires_at),
            peer=device_peer(),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "LINK_FRAME_TIME_INVALID"


def test_expired_queued_frame_is_not_delivered() -> None:
    link = relay()
    link.publish(
        frame(expires_at=NOW + timedelta(seconds=1)),
        peer=device_peer(),
        received_at=NOW,
    )

    assert (
        link.pull(
            peer=edge_peer(),
            received_at=NOW + timedelta(seconds=1),
            limit=1,
        )
        == ()
    )


def test_oversized_payload_is_rejected_before_frame_creation() -> None:
    with pytest.raises(TomatoLinkRejectedError) as rejected:
        frame(payload=b"x" * (MAXIMUM_OPAQUE_PAYLOAD_BYTES + 1))

    assert rejected.value.reason_code == "LINK_PAYLOAD_LENGTH_INVALID"


def test_destination_only_can_acknowledge_frame() -> None:
    link = relay()
    link.publish(frame(), peer=device_peer(), received_at=NOW)

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        link.acknowledge(
            "link-frame:01",
            peer=device_peer(),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "LINK_FRAME_NOT_QUEUED_FOR_PEER"


def test_queue_limit_rejects_new_frame_without_dropping_existing_frames() -> None:
    link = relay()
    for sequence in range(1, MAXIMUM_QUEUED_FRAMES_PER_ENDPOINT + 1):
        link.publish(
            frame(frame_id=f"link-frame:{sequence}", sequence=sequence),
            peer=device_peer(),
            received_at=NOW,
        )

    with pytest.raises(TomatoLinkRejectedError) as rejected:
        link.publish(
            frame(
                frame_id="link-frame:overflow",
                sequence=MAXIMUM_QUEUED_FRAMES_PER_ENDPOINT + 1,
            ),
            peer=device_peer(),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "LINK_DESTINATION_QUEUE_FULL"
    pulled = link.pull(peer=edge_peer(), received_at=NOW, limit=16)
    assert [item["frame_id"] for item in pulled] == [
        f"link-frame:{sequence}" for sequence in range(1, 17)
    ]


@pytest.mark.parametrize("limit", [0, 17])
def test_pull_limit_is_bounded(limit: int) -> None:
    with pytest.raises(TomatoLinkRejectedError) as rejected:
        relay().pull(peer=edge_peer(), received_at=NOW, limit=limit)

    assert rejected.value.reason_code == "LINK_PULL_LIMIT_INVALID"

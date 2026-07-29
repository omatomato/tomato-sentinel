import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from tomato_sentinel_device_protocol import (
    CardputerSimulator,
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    ProvisionedDevice,
    load_board_profile,
)
from tomato_sentinel_link_relay import (
    AuthenticatedRelayPeer,
    InMemoryTomatoLinkRelay,
    RelayEndpoint,
    RelayEndpointRole,
    TomatoLinkFrameValidator,
    build_opaque_frame,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
SECRET = b"remote-link-simulation-secret-32-bytes"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def protocol_stack() -> tuple[CardputerSimulator, DeviceMessageVerifier]:
    board = load_board_profile(
        load_json(PROFILES / "cardputer.original.v1.json"),
        load_json(SCHEMAS / "board-profile.schema.json"),
    )
    device = CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=SECRET,
        board_profile=board,
        firmware_version="0.3.0-sim",
        boot_id="boot:remote-link-01",
    )
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board,
            firmware_version="0.3.0-sim",
        ),
        SECRET,
    )
    verifier = DeviceMessageVerifier(
        DeviceProtocolValidator(
            envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
            payload_schemas={
                "text_command": load_json(SCHEMAS / "command.schema.json")
            },
        ),
        registry,
    )
    return device, verifier


def relay() -> InMemoryTomatoLinkRelay:
    return InMemoryTomatoLinkRelay(
        TomatoLinkFrameValidator(load_json(SCHEMAS / "tomato-link-frame.schema.json")),
        (
            RelayEndpoint(
                endpoint_id="cardputer:01",
                organization_id="org:01",
                role=RelayEndpointRole.DEVICE,
            ),
            RelayEndpoint(
                endpoint_id="edge:home-01",
                organization_id="org:01",
                role=RelayEndpointRole.EDGE,
            ),
        ),
    )


def device_peer() -> AuthenticatedRelayPeer:
    return AuthenticatedRelayPeer(
        endpoint_id="cardputer:01",
        organization_id="org:01",
        role=RelayEndpointRole.DEVICE,
        authenticated=True,
    )


def edge_peer() -> AuthenticatedRelayPeer:
    return AuthenticatedRelayPeer(
        endpoint_id="edge:home-01",
        organization_id="org:01",
        role=RelayEndpointRole.EDGE,
        authenticated=True,
    )


def command_payload() -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": "command:remote-status-01",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": "assistant",
        "action": "camera.status",
        "targets": ["camera:garage-01"],
        "parameters": {},
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "correlation_id": "correlation:remote-status-01",
    }


def encode(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def link_frame(payload: bytes) -> dict[str, object]:
    return build_opaque_frame(
        frame_id="link-frame:remote-status-01",
        organization_id="org:01",
        source_endpoint_id="cardputer:01",
        destination_endpoint_id="edge:home-01",
        session_id="link-session:remote-01",
        sequence=1,
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
        payload=payload,
    )


def test_signed_device_envelope_survives_opaque_remote_route_and_verifies() -> None:
    device, verifier = protocol_stack()
    envelope = device.text_command_message(
        command_payload(),
        sent_at=NOW,
        correlation_id="correlation:remote-status-01",
    )
    link = relay()
    link.publish(link_frame(encode(envelope)), peer=device_peer(), received_at=NOW)

    received_frames = link.pull(peer=edge_peer(), received_at=NOW, limit=1)
    inner = json.loads(
        base64.b64decode(cast(str, received_frames[0]["opaque_payload"])).decode()
    )
    verified = verifier.verify(inner, received_at=NOW)

    assert verified.device_id == "cardputer:01"
    assert verified.payload_type == "text_command"
    assert verified.payload["action"] == "camera.status"


def test_relay_acceptance_cannot_make_tampered_inner_envelope_trusted() -> None:
    device, verifier = protocol_stack()
    envelope = device.text_command_message(
        command_payload(),
        sent_at=NOW,
        correlation_id="correlation:remote-status-01",
    )
    envelope["correlation_id"] = "correlation:tampered"
    link = relay()
    receipt = link.publish(
        link_frame(encode(envelope)),
        peer=device_peer(),
        received_at=NOW,
    )
    received = link.pull(peer=edge_peer(), received_at=NOW, limit=1)[0]
    inner = json.loads(base64.b64decode(cast(str, received["opaque_payload"])).decode())

    with pytest.raises(DeviceMessageRejectedError) as rejected:
        verifier.verify(inner, received_at=NOW)

    assert receipt.state == "queued"
    assert rejected.value.reason_code == "AUTHENTICATION_INVALID"

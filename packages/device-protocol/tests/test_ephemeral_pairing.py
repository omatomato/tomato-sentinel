import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from tomato_sentinel_device_protocol import (
    EphemeralPairingParticipant,
    PairingRejectedError,
    PairingRole,
    PairingRoute,
    PairingState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
NOW = datetime(2026, 7, 29, 15, 0, tzinfo=UTC)
ROUTE = PairingRoute(
    organization_id="organization:01",
    source_endpoint_id="cardputer:01",
    destination_endpoint_id="edge:home-01",
)
DEVICE_PRIVATE = bytes.fromhex(
    "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
)
EDGE_PRIVATE = bytes.fromhex(
    "5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb"
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def participant(
    role: PairingRole,
    *,
    private_bytes: bytes,
    boot_id: str,
) -> EphemeralPairingParticipant:
    return EphemeralPairingParticipant(
        hello_schema=load_json(SCHEMAS / "tomato-link-pairing-hello.schema.json"),
        route=ROUTE,
        role=role,
        ceremony_id="link-pairing:01",
        boot_id=boot_id,
        created_at=NOW,
        ttl=timedelta(seconds=60),
        private_key=X25519PrivateKey.from_private_bytes(private_bytes),
    )


def peers() -> tuple[EphemeralPairingParticipant, EphemeralPairingParticipant]:
    return (
        participant(
            PairingRole.DEVICE,
            private_bytes=DEVICE_PRIVATE,
            boot_id="boot:device-01",
        ),
        participant(
            PairingRole.EDGE,
            private_bytes=EDGE_PRIVATE,
            boot_id="boot:edge-01",
        ),
    )


def exchange(
    device: EphemeralPairingParticipant,
    edge: EphemeralPairingParticipant,
) -> str:
    device_fingerprint = device.receive_peer_hello(edge.hello(), received_at=NOW)
    edge_fingerprint = edge.receive_peer_hello(device.hello(), received_at=NOW)
    assert device_fingerprint == edge_fingerprint
    return device_fingerprint


def confirm(
    participant: EphemeralPairingParticipant,
    fingerprint: str,
) -> None:
    participant.confirm_fingerprint(
        fingerprint,
        confirmed_at=NOW,
        confirmation_source="physical_display",
    )


def test_two_physically_confirmed_endpoints_install_same_one_shot_root() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)
    confirm(device, fingerprint)
    confirm(edge, fingerprint)
    installed: list[tuple[str, bytes]] = []

    device.consume_root_secret(
        lambda key_id, secret: installed.append((key_id, secret)),
        consumed_at=NOW,
    )
    edge.consume_root_secret(
        lambda key_id, secret: installed.append((key_id, secret)),
        consumed_at=NOW,
    )

    assert installed[0] == installed[1]
    assert len(installed[0][1]) == 32
    assert device.status.state is PairingState.CONSUMED
    assert edge.status.state is PairingState.CONSUMED
    assert fingerprint == "8933-a60c-daee-7334-bcea-de81-de68-b085"
    assert DEVICE_PRIVATE.hex() not in repr(device)
    assert installed[0][1].hex() not in repr(device)


def test_exact_peer_hello_retry_is_idempotent_but_changed_retry_is_denied() -> None:
    device, edge = peers()
    hello = edge.hello()
    first = device.receive_peer_hello(hello, received_at=NOW)
    retry = device.receive_peer_hello(hello, received_at=NOW)
    changed = dict(hello)
    changed["boot_id"] = "boot:edge-changed"

    with pytest.raises(PairingRejectedError) as rejected:
        device.receive_peer_hello(changed, received_at=NOW)

    assert retry == first
    assert rejected.value.reason_code == "PAIRING_PEER_HELLO_CHANGED"


def test_wrong_fingerprint_does_not_install_or_consume_root() -> None:
    device, edge = peers()
    exchange(device, edge)

    with pytest.raises(PairingRejectedError) as rejected:
        confirm(device, "0000-0000-0000-0000-0000-0000-0000-0000")
    with pytest.raises(PairingRejectedError) as unavailable:
        device.consume_root_secret(lambda _key, _secret: None, consumed_at=NOW)

    assert rejected.value.reason_code == "PAIRING_FINGERPRINT_MISMATCH"
    assert unavailable.value.reason_code == "PAIRING_ROOT_NOT_AVAILABLE"
    assert device.status.state is PairingState.AWAITING_CONFIRMATION


def test_non_physical_confirmation_is_denied() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)

    with pytest.raises(PairingRejectedError) as rejected:
        device.confirm_fingerprint(
            fingerprint,
            confirmed_at=NOW,
            confirmation_source="remote_api",
        )

    assert rejected.value.reason_code == "PAIRING_CONFIRMATION_SOURCE_INVALID"


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("participant_role", "device", "PAIRING_PEER_ROLE_INVALID"),
        ("organization_id", "organization:other", "PAIRING_ROUTE_MISMATCH"),
        ("ceremony_id", "link-pairing:other", "PAIRING_ROUTE_MISMATCH"),
    ],
)
def test_wrong_role_or_route_is_denied(
    field: str,
    value: str,
    reason_code: str,
) -> None:
    device, edge = peers()
    hello = edge.hello()
    hello[field] = value

    with pytest.raises(PairingRejectedError) as rejected:
        device.receive_peer_hello(hello, received_at=NOW)

    assert rejected.value.reason_code == reason_code


def test_unknown_hello_field_is_denied() -> None:
    device, edge = peers()
    hello = edge.hello()
    hello["root_secret"] = "must-not-cross-contract"

    with pytest.raises(PairingRejectedError) as rejected:
        device.receive_peer_hello(hello, received_at=NOW)

    assert rejected.value.reason_code == "PAIRING_HELLO_INVALID"


def test_peer_window_must_also_be_bounded() -> None:
    device, edge = peers()
    hello = edge.hello()
    hello["expires_at"] = "2026-07-29T15:05:00Z"

    with pytest.raises(PairingRejectedError) as rejected:
        device.receive_peer_hello(hello, received_at=NOW)

    assert rejected.value.reason_code == "PAIRING_PEER_WINDOW_INVALID"


def test_reflected_public_key_is_denied() -> None:
    device, edge = peers()
    reflected = edge.hello()
    reflected["ephemeral_public_key_base64"] = device.hello()[
        "ephemeral_public_key_base64"
    ]

    with pytest.raises(PairingRejectedError) as rejected:
        device.receive_peer_hello(reflected, received_at=NOW)

    assert rejected.value.reason_code == "PAIRING_REFLECTED_KEY"


def test_low_order_public_key_is_denied_during_derivation() -> None:
    device, edge = peers()
    hello = edge.hello()
    hello["ephemeral_public_key_base64"] = (
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )
    fingerprint = device.receive_peer_hello(hello, received_at=NOW)

    with pytest.raises(PairingRejectedError) as rejected:
        confirm(device, fingerprint)

    assert rejected.value.reason_code == "PAIRING_SHARED_SECRET_INVALID"


def test_expiry_clears_unconsumed_root_and_is_terminal() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)
    confirm(device, fingerprint)

    status = device.expire(now=NOW + timedelta(seconds=60))
    with pytest.raises(PairingRejectedError) as rejected:
        device.consume_root_secret(
            lambda _key, _secret: None,
            consumed_at=NOW + timedelta(seconds=60),
        )

    assert status.state is PairingState.EXPIRED
    assert status.reason_code == "PAIRING_WINDOW_EXPIRED"
    assert rejected.value.reason_code == "PAIRING_TERMINAL"


def test_reboot_and_cancel_are_fail_closed() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)
    confirm(device, fingerprint)

    status = device.reset_for_reboot()
    with pytest.raises(PairingRejectedError) as rejected:
        device.consume_root_secret(lambda _key, _secret: None, consumed_at=NOW)

    assert status.state is PairingState.CANCELLED
    assert status.reason_code == "PAIRING_BOOT_CHANGED"
    assert rejected.value.reason_code == "PAIRING_TERMINAL"


def test_consumption_is_one_shot() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)
    confirm(device, fingerprint)
    device.consume_root_secret(lambda _key, _secret: None, consumed_at=NOW)

    with pytest.raises(PairingRejectedError) as rejected:
        device.consume_root_secret(lambda _key, _secret: None, consumed_at=NOW)

    assert rejected.value.reason_code == "PAIRING_TERMINAL"


@pytest.mark.parametrize("ttl_seconds", [29, 121])
def test_pairing_ttl_is_bounded(ttl_seconds: int) -> None:
    with pytest.raises(PairingRejectedError) as rejected:
        EphemeralPairingParticipant(
            hello_schema=load_json(SCHEMAS / "tomato-link-pairing-hello.schema.json"),
            route=ROUTE,
            role=PairingRole.DEVICE,
            ceremony_id="link-pairing:01",
            boot_id="boot:device-01",
            created_at=NOW,
            ttl=timedelta(seconds=ttl_seconds),
        )

    assert rejected.value.reason_code == "PAIRING_TTL_INVALID"


def test_sink_failure_does_not_claim_consumption_and_can_retry() -> None:
    device, edge = peers()
    fingerprint = exchange(device, edge)
    confirm(device, fingerprint)

    def fail(_key_id: str, _secret: bytes) -> None:
        raise RuntimeError("simulated atomic install failure")

    with pytest.raises(RuntimeError):
        device.consume_root_secret(fail, consumed_at=NOW)
    installed: list[str] = []
    device.consume_root_secret(
        lambda key_id, _secret: installed.append(key_id),
        consumed_at=NOW,
    )

    assert installed == ["link-root-key:8933a60cdaee7334"]
    assert device.status.state is PairingState.CONSUMED

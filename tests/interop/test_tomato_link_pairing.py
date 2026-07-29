import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from tomato_sentinel_device_protocol import (
    EphemeralPairingParticipant,
    PairingRole,
    PairingRoute,
)
from tomato_sentinel_device_protocol.ephemeral_pairing import _canonical_transcript
from tomato_sentinel_link_relay import (
    GovernedTomatoLinkCodec,
    InMemoryLinkCredentialVault,
    LinkRoute,
    LinkSessionAuthority,
    TomatoLinkBinding,
    TomatoLinkSealedPayloadCodec,
)

ROOT = Path(__file__).parents[2]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
FIXTURE = ROOT / "tests" / "interop" / "fixtures" / "tomato-link-pairing-v1.json"
NOW = datetime(2026, 7, 29, 15, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def build_pair() -> tuple[
    EphemeralPairingParticipant,
    EphemeralPairingParticipant,
]:
    vector = load_json(FIXTURE)
    fields = vector["hello_fields"]
    assert isinstance(fields, dict)
    route = PairingRoute(
        organization_id=str(fields["organization_id"]),
        source_endpoint_id=str(fields["source_endpoint_id"]),
        destination_endpoint_id=str(fields["destination_endpoint_id"]),
    )
    schema = load_json(SCHEMAS / "tomato-link-pairing-hello.schema.json")
    return (
        EphemeralPairingParticipant(
            hello_schema=schema,
            route=route,
            role=PairingRole.DEVICE,
            ceremony_id=str(fields["ceremony_id"]),
            boot_id=str(fields["device_boot_id"]),
            created_at=NOW,
            ttl=timedelta(seconds=60),
            private_key=X25519PrivateKey.from_private_bytes(
                bytes.fromhex(str(vector["device_private_key_hex"]))
            ),
        ),
        EphemeralPairingParticipant(
            hello_schema=schema,
            route=route,
            role=PairingRole.EDGE,
            ceremony_id=str(fields["ceremony_id"]),
            boot_id=str(fields["edge_boot_id"]),
            created_at=NOW,
            ttl=timedelta(seconds=60),
            private_key=X25519PrivateKey.from_private_bytes(
                bytes.fromhex(str(vector["edge_private_key_hex"]))
            ),
        ),
    )


def test_language_neutral_x25519_hkdf_vector_is_stable() -> None:
    vector = load_json(FIXTURE)
    device, edge = build_pair()
    device_hello = device.hello()
    edge_hello = edge.hello()
    transcript_hash = hashlib.sha256(
        _canonical_transcript(device_hello, edge_hello)
    ).hexdigest()
    fingerprint = device.receive_peer_hello(edge_hello, received_at=NOW)
    edge.receive_peer_hello(device_hello, received_at=NOW)
    device.confirm_fingerprint(
        fingerprint,
        confirmed_at=NOW,
        confirmation_source="physical_display",
    )
    installed: list[tuple[str, bytes]] = []
    device.consume_root_secret(
        lambda key_id, secret: installed.append((key_id, secret)),
        consumed_at=NOW,
    )

    device_public = X25519PrivateKey.from_private_bytes(
        bytes.fromhex(str(vector["device_private_key_hex"]))
    ).public_key()
    edge_public = X25519PrivateKey.from_private_bytes(
        bytes.fromhex(str(vector["edge_private_key_hex"]))
    ).public_key()
    shared = X25519PrivateKey.from_private_bytes(
        bytes.fromhex(str(vector["device_private_key_hex"]))
    ).exchange(edge_public)

    assert (
        base64.b64encode(
            device_public.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode("ascii")
        == vector["device_public_key_base64"]
    )
    assert (
        base64.b64encode(
            edge_public.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode("ascii")
        == vector["edge_public_key_base64"]
    )
    assert shared.hex() == vector["shared_secret_hex"]
    assert transcript_hash == vector["transcript_sha256"]
    assert fingerprint == vector["display_fingerprint"]
    assert installed[0][0] == vector["root_key_id"]
    assert installed[0][1].hex() == vector["root_secret_hex"]


def test_pairing_output_drives_existing_governed_encrypted_session() -> None:
    device, edge = build_pair()
    fingerprint = device.receive_peer_hello(edge.hello(), received_at=NOW)
    assert edge.receive_peer_hello(device.hello(), received_at=NOW) == fingerprint
    for endpoint in (device, edge):
        endpoint.confirm_fingerprint(
            fingerprint,
            confirmed_at=NOW,
            confirmation_source="physical_display",
        )

    route = LinkRoute(
        organization_id=device.route.organization_id,
        source_endpoint_id=device.route.source_endpoint_id,
        destination_endpoint_id=device.route.destination_endpoint_id,
    )
    device_vault = InMemoryLinkCredentialVault()
    edge_vault = InMemoryLinkCredentialVault()
    device.consume_root_secret(
        lambda key_id, secret: device_vault.provision(
            route,
            key_id=key_id,
            secret=secret,
        ),
        consumed_at=NOW,
    )
    edge.consume_root_secret(
        lambda key_id, secret: edge_vault.provision(
            route,
            key_id=key_id,
            secret=secret,
        ),
        consumed_at=NOW,
    )
    lease_schema = load_json(SCHEMAS / "tomato-link-session-lease.schema.json")
    device_authority = LinkSessionAuthority(
        lease_schema,
        device_vault,
        salt_source=lambda _: b"\x41" * 32,
    )
    edge_authority = LinkSessionAuthority(
        lease_schema,
        edge_vault,
        salt_source=lambda _: b"\x41" * 32,
    )
    issued = device_authority.issue(
        lease_id="link-lease:paired-01",
        session_id="link-session:paired-01",
        route=route,
        now=NOW,
        ttl=timedelta(seconds=60),
    )
    accepted = edge_authority.accept(issued.lease_contract, received_at=NOW)
    binding = TomatoLinkBinding(
        frame_id="link-frame:paired-01",
        organization_id=route.organization_id,
        source_endpoint_id=route.source_endpoint_id,
        destination_endpoint_id=route.destination_endpoint_id,
        session_id=issued.lease.session_id,
        sequence=1,
        created_at="2026-07-29T15:00:00Z",
        expires_at="2026-07-29T15:01:00Z",
    )
    sealed_codec = TomatoLinkSealedPayloadCodec(
        load_json(SCHEMAS / "tomato-link-sealed-payload.schema.json"),
        nonce_source=lambda _: b"\x42" * 12,
    )
    sealed = GovernedTomatoLinkCodec(sealed_codec, device_vault).seal(
        b"signed-device-envelope",
        binding=binding,
        session=issued,
        now=NOW,
    )

    opened = GovernedTomatoLinkCodec(sealed_codec, edge_vault).open(
        sealed,
        binding=binding,
        session=accepted,
        now=NOW,
    )

    assert opened == b"signed-device-envelope"

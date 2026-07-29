import base64
import json
from pathlib import Path
from typing import Any

import pytest
from tomato_sentinel_link_relay import (
    MAXIMUM_SEALED_PLAINTEXT_BYTES,
    TomatoLinkBinding,
    TomatoLinkSealedPayloadCodec,
    TomatoLinkSealRejectedError,
    TomatoLinkSessionKey,
)

ROOT = Path(__file__).parents[3]
SCHEMA = (
    ROOT
    / "packages"
    / "contracts"
    / "schemas"
    / "v1"
    / "tomato-link-sealed-payload.schema.json"
)
KEY_BYTES = bytes(range(32))


def load_schema() -> dict[str, Any]:
    with SCHEMA.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def binding(**changes: object) -> TomatoLinkBinding:
    values: dict[str, object] = {
        "frame_id": "link-frame:01",
        "organization_id": "organization:01",
        "source_endpoint_id": "cardputer:01",
        "destination_endpoint_id": "edge:home-01",
        "session_id": "link-session:01",
        "sequence": 1,
        "created_at": "2026-07-29T12:00:00Z",
        "expires_at": "2026-07-29T12:01:00Z",
    }
    values.update(changes)
    return TomatoLinkBinding(**values)  # type: ignore[arg-type]


def session_key(**changes: object) -> TomatoLinkSessionKey:
    values: dict[str, object] = {
        "key_id": "link-key:01",
        "organization_id": "organization:01",
        "source_endpoint_id": "cardputer:01",
        "session_id": "link-session:01",
        "destination_endpoint_id": "edge:home-01",
        "key": KEY_BYTES,
    }
    values.update(changes)
    return TomatoLinkSessionKey(**values)  # type: ignore[arg-type]


def codec(nonces: list[bytes] | None = None) -> TomatoLinkSealedPayloadCodec:
    if nonces is None:
        return TomatoLinkSealedPayloadCodec(load_schema())
    return TomatoLinkSealedPayloadCodec(
        load_schema(),
        nonce_source=lambda _: nonces.pop(0),
    )


def test_payload_round_trip_uses_authenticated_encryption() -> None:
    seal = codec([b"\x01" * 12])
    plaintext = b'{"action":"camera.status"}'

    encoded = seal.seal(plaintext, binding=binding(), session_key=session_key())
    opened = seal.open(encoded, binding=binding(), session_key=session_key())
    envelope = json.loads(encoded)

    assert opened == plaintext
    assert envelope["algorithm"] == "AES-256-GCM"
    assert plaintext not in encoded
    assert len(base64.b64decode(envelope["ciphertext_base64"])) == len(plaintext) + 16


@pytest.mark.parametrize(
    ("changed_binding", "reason_code"),
    [
        (
            {"organization_id": "organization:other"},
            "LINK_SEAL_KEY_BINDING_MISMATCH",
        ),
        (
            {"source_endpoint_id": "cardputer:forged"},
            "LINK_SEAL_KEY_BINDING_MISMATCH",
        ),
        ({"frame_id": "link-frame:other"}, "LINK_SEAL_AUTHENTICATION_INVALID"),
        ({"sequence": 2}, "LINK_SEAL_AUTHENTICATION_INVALID"),
        (
            {"expires_at": "2026-07-29T12:02:00Z"},
            "LINK_SEAL_AUTHENTICATION_INVALID",
        ),
    ],
)
def test_changed_routing_metadata_fails_authentication(
    changed_binding: dict[str, object],
    reason_code: str,
) -> None:
    seal = codec([b"\x02" * 12])
    encoded = seal.seal(b"sensitive", binding=binding(), session_key=session_key())

    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        seal.open(
            encoded,
            binding=binding(**changed_binding),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == reason_code


def test_ciphertext_tampering_fails_authentication() -> None:
    seal = codec([b"\x03" * 12])
    encoded = seal.seal(b"sensitive", binding=binding(), session_key=session_key())
    envelope = json.loads(encoded)
    ciphertext = bytearray(base64.b64decode(envelope["ciphertext_base64"]))
    ciphertext[0] ^= 1
    envelope["ciphertext_base64"] = base64.b64encode(ciphertext).decode()

    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        seal.open(
            json.dumps(envelope).encode(),
            binding=binding(),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == "LINK_SEAL_AUTHENTICATION_INVALID"


def test_nonce_reuse_is_denied_before_encryption() -> None:
    seal = codec([b"\x04" * 12, b"\x04" * 12])
    seal.seal(b"first", binding=binding(), session_key=session_key())

    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        seal.seal(
            b"second",
            binding=binding(frame_id="link-frame:02", sequence=2),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == "LINK_SEAL_NONCE_REUSED"


@pytest.mark.parametrize(
    "binding_change",
    [
        {"organization_id": "organization:other"},
        {"source_endpoint_id": "cardputer:other"},
        {"session_id": "link-session:other"},
        {"destination_endpoint_id": "edge:other"},
    ],
)
def test_key_is_bound_to_route_and_session(
    binding_change: dict[str, object],
) -> None:
    seal = codec([b"\x05" * 12])

    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        seal.seal(
            b"sensitive",
            binding=binding(**binding_change),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == "LINK_SEAL_KEY_BINDING_MISMATCH"


def test_key_material_is_redacted_from_repr() -> None:
    key = session_key(key=b"s" * 32)

    assert "ssss" not in repr(key)
    assert "<redacted>" in repr(key)


@pytest.mark.parametrize(
    "plaintext", [b"", b"x" * (MAXIMUM_SEALED_PLAINTEXT_BYTES + 1)]
)
def test_empty_or_oversized_plaintext_is_denied(plaintext: bytes) -> None:
    with pytest.raises(TomatoLinkSealRejectedError) as rejected:
        codec([b"\x06" * 12]).seal(
            plaintext,
            binding=binding(),
            session_key=session_key(),
        )

    assert rejected.value.reason_code == "LINK_SEAL_PLAINTEXT_LENGTH_INVALID"

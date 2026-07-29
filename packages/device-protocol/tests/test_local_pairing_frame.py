import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from tomato_sentinel_device_protocol import (
    LOCAL_PAIRING_FRAME_HEADER_BYTES,
    MAXIMUM_LOCAL_PAIRING_FRAME_BYTES,
    EphemeralPairingParticipant,
    LocalPairingFrame,
    LocalPairingFrameDecoder,
    LocalPairingFrameRejectedError,
    LocalPairingFrameType,
    PairingRole,
    PairingRoute,
    PairingState,
    decode_local_pairing_frame,
    encode_local_pairing_frame,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages/contracts/schemas/v1"
VECTOR_PAYLOAD = b'{"contract_version":1,"pairing_version":1}'
VECTOR_HEX = (
    "54534c500101000000000001002a000035a1e0a1"
    "7b22636f6e74726163745f76657273696f6e223a312c"
    "2270616972696e675f76657273696f6e223a317d"
)
VECTOR_FIXTURE = ROOT / "tests/interop/fixtures/tomato-link-local-frame-v1.json"
NOW = datetime(2026, 7, 29, 15, 0, tzinfo=UTC)
ROUTE = PairingRoute(
    organization_id="organization:01",
    source_endpoint_id="cardputer:01",
    destination_endpoint_id="edge:home-01",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def participant(
    role: PairingRole,
    private_key_hex: str,
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
        private_key=X25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex)),
    )


def assert_rejected(encoded: bytes, reason_code: str) -> None:
    with pytest.raises(LocalPairingFrameRejectedError) as rejected:
        decode_local_pairing_frame(encoded)
    assert rejected.value.reason_code == reason_code


def test_published_hello_vector_round_trips_exact_bytes() -> None:
    fixture = load_json(VECTOR_FIXTURE)
    frame = LocalPairingFrame(
        frame_type=LocalPairingFrameType.HELLO,
        sequence=1,
        payload=VECTOR_PAYLOAD,
    )

    encoded = encode_local_pairing_frame(frame)

    assert fixture["payload_utf8"] == VECTOR_PAYLOAD.decode()
    assert fixture["encoded_frame_hex"] == VECTOR_HEX
    assert encoded.hex() == fixture["encoded_frame_hex"]
    assert decode_local_pairing_frame(encoded) == frame
    assert repr(frame) == (
        "LocalPairingFrame(frame_type=<LocalPairingFrameType.HELLO: 1>, sequence=1)"
    )


def test_real_public_hello_crosses_frame_before_domain_validation() -> None:
    device = participant(
        PairingRole.DEVICE,
        "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a",
        "boot:device-01",
    )
    edge = participant(
        PairingRole.EDGE,
        "5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb",
        "boot:edge-01",
    )
    payload = json.dumps(
        edge.hello(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")

    decoded = decode_local_pairing_frame(
        encode_local_pairing_frame(
            LocalPairingFrame(LocalPairingFrameType.HELLO, 1, payload)
        )
    )
    fingerprint = device.receive_peer_hello(
        json.loads(decoded.payload),
        received_at=NOW,
    )

    assert fingerprint == "8933-a60c-daee-7334-bcea-de81-de68-b085"
    assert device.status.state is PairingState.AWAITING_CONFIRMATION


def test_incremental_decoder_accepts_one_exact_fragmented_frame() -> None:
    encoded = bytes.fromhex(VECTOR_HEX)
    decoder = LocalPairingFrameDecoder()
    decoded = None

    for byte in encoded:
        decoded = decoder.feed(bytes([byte]))

    assert decoded == LocalPairingFrame(
        LocalPairingFrameType.HELLO,
        1,
        VECTOR_PAYLOAD,
    )
    assert decoder.buffered_bytes == 0
    with pytest.raises(LocalPairingFrameRejectedError) as second:
        decoder.feed(b"x")
    assert second.value.reason_code == "PAIRING_FRAME_ALREADY_COMPLETE"


def test_empty_cancel_is_the_only_valid_cancel_shape() -> None:
    cancel = LocalPairingFrame(LocalPairingFrameType.CANCEL, 7, b"")

    assert decode_local_pairing_frame(encode_local_pairing_frame(cancel)) == cancel
    with pytest.raises(LocalPairingFrameRejectedError) as rejected:
        encode_local_pairing_frame(
            LocalPairingFrame(LocalPairingFrameType.CANCEL, 7, b"arbitrary")
        )
    assert rejected.value.reason_code == "PAIRING_FRAME_CANCEL_PAYLOAD_INVALID"


@pytest.mark.parametrize(
    ("offset", "replacement", "reason_code"),
    [
        (0, 0x00, "PAIRING_FRAME_MAGIC_INVALID"),
        (4, 0x02, "PAIRING_FRAME_VERSION_UNSUPPORTED"),
        (5, 0x7F, "PAIRING_FRAME_TYPE_UNSUPPORTED"),
        (6, 0x01, "PAIRING_FRAME_FLAGS_INVALID"),
        (11, 0x00, "PAIRING_FRAME_SEQUENCE_INVALID"),
        (14, 0x01, "PAIRING_FRAME_RESERVED_INVALID"),
        (16, 0x00, "PAIRING_FRAME_CHECKSUM_INVALID"),
    ],
)
def test_corrupt_header_fields_are_denied(
    offset: int,
    replacement: int,
    reason_code: str,
) -> None:
    corrupted = bytearray.fromhex(VECTOR_HEX)
    corrupted[offset] = replacement

    assert_rejected(bytes(corrupted), reason_code)


def test_declared_oversize_truncation_and_trailing_bytes_are_denied() -> None:
    oversized = bytearray.fromhex(VECTOR_HEX)
    oversized[12:14] = (1025).to_bytes(2, "big")

    assert_rejected(bytes(oversized), "PAIRING_FRAME_PAYLOAD_TOO_LARGE")
    assert_rejected(bytes.fromhex(VECTOR_HEX)[:-1], "PAIRING_FRAME_LENGTH_MISMATCH")
    assert_rejected(
        bytes.fromhex(VECTOR_HEX) + b"x",
        "PAIRING_FRAME_LENGTH_MISMATCH",
    )
    assert_rejected(
        bytes.fromhex(VECTOR_HEX)[: LOCAL_PAIRING_FRAME_HEADER_BYTES - 1],
        "PAIRING_FRAME_HEADER_INCOMPLETE",
    )


def test_incremental_decoder_latches_overflow_corruption_and_cancel() -> None:
    overflow = LocalPairingFrameDecoder()
    with pytest.raises(LocalPairingFrameRejectedError) as too_large:
        overflow.feed(b"x" * (MAXIMUM_LOCAL_PAIRING_FRAME_BYTES + 1))
    assert too_large.value.reason_code == "PAIRING_FRAME_BUFFER_OVERFLOW"
    with pytest.raises(LocalPairingFrameRejectedError) as still_terminal:
        overflow.feed(b"")
    assert still_terminal.value.reason_code == "PAIRING_FRAME_BUFFER_OVERFLOW"

    corrupted = LocalPairingFrameDecoder()
    with pytest.raises(LocalPairingFrameRejectedError) as bad_magic:
        corrupted.feed(b"BAD!" + bytes.fromhex(VECTOR_HEX)[4:])
    assert bad_magic.value.reason_code == "PAIRING_FRAME_MAGIC_INVALID"
    assert corrupted.buffered_bytes == 0

    cancelled = LocalPairingFrameDecoder()
    assert cancelled.feed(bytes.fromhex(VECTOR_HEX)[:8]) is None
    cancelled.cancel()
    assert cancelled.buffered_bytes == 0
    with pytest.raises(LocalPairingFrameRejectedError) as cancelled_feed:
        cancelled.feed(bytes.fromhex(VECTOR_HEX)[8:])
    assert cancelled_feed.value.reason_code == "PAIRING_FRAME_CANCELLED"

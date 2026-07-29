import base64
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SKETCH_DIR = ROOT / "firmware/cardputer/app/TomatoSentinel"
CRYPTO_HEADER = SKETCH_DIR / "TomatoLinkCrypto.h"
CRYPTO_SOURCE = SKETCH_DIR / "TomatoLinkCrypto.cpp"
SELF_TEST = SKETCH_DIR / "TomatoLinkCryptoSelfTest.cpp"
VECTOR_HEADER = SKETCH_DIR / "TomatoLinkCryptoInteropVector.h"
LOCAL_FRAME_HEADER = SKETCH_DIR / "TomatoLinkLocalFrame.h"
LOCAL_FRAME_SOURCE = SKETCH_DIR / "TomatoLinkLocalFrame.cpp"
LOCAL_FRAME_SELF_TEST = SKETCH_DIR / "TomatoLinkLocalFrameSelfTest.cpp"
LOCAL_FRAME_VECTOR = SKETCH_DIR / "TomatoLinkLocalFrameInteropVector.h"
SKETCH = SKETCH_DIR / "TomatoSentinel.ino"
UI = SKETCH_DIR / "TomatoSentinelUi.h"
SAFE_BUILD = ROOT / "firmware/cardputer/build-safe.sh"
INTEROP_BUILD = ROOT / "firmware/cardputer/build-crypto-interop.sh"
VECTOR_FIXTURE = ROOT / "tests/interop/fixtures/tomato-link-pairing-v1.json"
LOCAL_FRAME_FIXTURE = ROOT / "tests/interop/fixtures/tomato-link-local-frame-v1.json"


def _hex_array(source: str, name: str) -> bytes:
    match = re.search(
        rf"constexpr uint8_t {name}\[[^\]]*\] = \{{(?P<body>.*?)\}};",
        source,
        re.DOTALL,
    )
    assert match is not None
    values = re.findall(r"0x([0-9a-f]{2})", match["body"])
    return bytes(int(value, 16) for value in values)


def test_cpp_vector_exactly_matches_language_neutral_fixture() -> None:
    fixture = json.loads(VECTOR_FIXTURE.read_text())
    vector = VECTOR_HEADER.read_text()

    assert (
        _hex_array(vector, "kDevicePrivate").hex() == fixture["device_private_key_hex"]
    )
    assert _hex_array(vector, "kDevicePublic") == base64.b64decode(
        fixture["device_public_key_base64"], validate=True
    )
    assert _hex_array(vector, "kEdgePrivate").hex() == fixture["edge_private_key_hex"]
    assert _hex_array(vector, "kEdgePublic") == base64.b64decode(
        fixture["edge_public_key_base64"], validate=True
    )
    assert _hex_array(vector, "kSharedSecret").hex() == fixture["shared_secret_hex"]
    assert _hex_array(vector, "kTranscriptDigest").hex() == fixture["transcript_sha256"]
    assert _hex_array(vector, "kRoot").hex() == fixture["root_secret_hex"]
    assert f'"{fixture["display_fingerprint"]}"' in vector

    transcript_match = re.search(
        r'R"json\((?P<transcript>.*)\)json";', vector, re.DOTALL
    )
    assert transcript_match is not None
    transcript = transcript_match["transcript"].encode()
    assert len(transcript) == 892
    assert hashlib.sha256(transcript).hexdigest() == fixture["transcript_sha256"]


def test_crypto_adapter_is_bounded_allocation_free_and_fail_closed() -> None:
    header = CRYPTO_HEADER.read_text()
    source = CRYPTO_SOURCE.read_text()
    self_test = SELF_TEST.read_text()
    combined = header + source + self_test

    assert "kMaxTranscriptSize = 2048" in header
    assert "RandomCallback" in header
    assert "MBEDTLS_ECP_DP_CURVE25519_ENABLED" in source
    assert "mbedtls_ecp_check_pubkey" in source
    assert "isAllZero(shared_secret" in source
    assert "mbedtls_sha256" in source
    assert "mbedtls_md_hmac" in source
    assert "secureClear(shared_secret" in source
    assert "secureClear(root" in source
    assert "Result::transcript_too_large" in source
    assert "kLowOrderPublic" in self_test
    assert "low_order_peer_not_rejected" in self_test
    assert "transcript_bound_not_enforced" in self_test
    assert "new " not in combined
    assert "malloc" not in combined
    assert "std::vector" not in combined
    assert "String" not in combined


def test_cpp_local_frame_matches_python_vector_and_denial_controls() -> None:
    fixture = json.loads(LOCAL_FRAME_FIXTURE.read_text())
    vector = LOCAL_FRAME_VECTOR.read_text()
    header = LOCAL_FRAME_HEADER.read_text()
    source = LOCAL_FRAME_SOURCE.read_text()
    self_test = LOCAL_FRAME_SELF_TEST.read_text()

    expected = bytes.fromhex(fixture["encoded_frame_hex"])
    assert _hex_array(vector, "kEncoded") == expected
    assert "kMaximumPayloadSize = 1024" in header
    assert "kHeaderSize = 20" in header
    assert "0xEDB88320U" in source
    assert "flags_invalid" in source
    assert "reserved_invalid" in source
    assert "payload_too_large" in source
    assert "checksum_invalid" in source
    assert "buffer_overflow" in source
    assert "cancel_payload_invalid" in source
    assert "checksum_not_rejected" in self_test
    assert "oversize_not_rejected" in self_test
    assert "cancel_payload_not_rejected" in self_test
    assert "buffer_overflow_not_rejected" in self_test
    assert "cancel_not_terminal" in self_test


def test_interop_image_is_visibly_isolated_and_non_deployable() -> None:
    sketch = SKETCH.read_text()
    ui = UI.read_text()
    default_build = SAFE_BUILD.read_text()
    interop_build = INTEROP_BUILD.read_text()

    assert "TOMATO_INTEROP_NON_DEPLOYABLE" in sketch
    assert "#error" in sketch
    assert "TOMATO_CRYPTO_INTEROP_SELF_TEST=1" in interop_build
    assert "TOMATO_LOCAL_FRAME_INTEROP_SELF_TEST=1" in interop_build
    assert "TOMATO_INTEROP_NON_DEPLOYABLE=1" in interop_build
    assert "TOMATO_CRYPTO_INTEROP_SELF_TEST=1" not in default_build
    assert "--upload" not in interop_build
    assert "write-flash" not in interop_build
    assert "-DTOMATO_RUNTIME_WRITE_GUARDS=1" in interop_build
    assert "-DTOMATO_TARGET_CARDPUTER_ORIGINAL=1" in interop_build
    assert "else if (kInteropEvidenceBuild)" in sketch
    assert "!kInteropEvidenceBuild" in sketch
    assert "keyboard.begin(millis());" in sketch
    assert "PAIRING VECTORS" in ui
    assert "SELF-TEST PASS" in ui
    assert "NO PAIRING / NO STORAGE" in ui
    assert "COMPILE-ONLY" in ui
    assert "secrets=not_logged" in sketch


def test_interop_sources_do_not_add_transport_storage_or_secret_logging() -> None:
    sources = "".join(
        path.read_text()
        for path in [
            CRYPTO_HEADER,
            CRYPTO_SOURCE,
            SELF_TEST,
            VECTOR_HEADER,
            LOCAL_FRAME_HEADER,
            LOCAL_FRAME_SOURCE,
            LOCAL_FRAME_SELF_TEST,
            LOCAL_FRAME_VECTOR,
            INTEROP_BUILD,
        ]
    )
    prohibited = [
        "#include <WiFi.h>",
        "#include <WebServer.h>",
        "#include <Preferences.h>",
        "esp_wifi_",
        "nvs_set",
        "nvs_commit",
        "esp_partition_write(",
        "esp_flash_write(",
        "Serial.print(private",
        "Serial.print(shared",
        "Serial.print(root",
        "HWCDCSerial.print(private",
        "HWCDCSerial.print(shared",
        "HWCDCSerial.print(root",
    ]
    assert not any(item in sources for item in prohibited)

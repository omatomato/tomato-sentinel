import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_device_protocol import (
    MAXIMUM_CAPTURE_DURATION_MS,
    MAXIMUM_ENCODED_AUDIO_BYTES,
    AudioCaptureLimitError,
    AudioCaptureState,
    BoardProfile,
    CardputerSimulator,
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    ProvisionedDevice,
    PushToTalkRecorder,
    load_board_profile,
    sign_envelope,
)
from tomato_sentinel_policy import Profile

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 25, 18, 40, tzinfo=UTC)
SECRET = b"simulation-device-key-material-32-bytes"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def board(name: str = "cardputer.original.v1.json") -> BoardProfile:
    return load_board_profile(
        load_json(PROFILES / name),
        load_json(SCHEMAS / "board-profile.schema.json"),
    )


def validator() -> DeviceProtocolValidator:
    return DeviceProtocolValidator(
        envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
        payload_schemas={
            "capability_report": load_json(SCHEMAS / "capability-report.schema.json"),
            "profile_state": load_json(SCHEMAS / "profile-state.schema.json"),
            "text_command": load_json(SCHEMAS / "command.schema.json"),
            "voice_command": load_json(SCHEMAS / "voice-command.schema.json"),
            "cancel_request": load_json(SCHEMAS / "cancel-request.schema.json"),
        },
    )


def simulator(
    *,
    profile_name: str = "cardputer.original.v1.json",
) -> CardputerSimulator:
    return CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=SECRET,
        board_profile=board(profile_name),
        firmware_version="0.1.0-sim",
        boot_id="boot:01",
    )


def verifier(
    *,
    revoked: bool = False,
) -> DeviceMessageVerifier:
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board(),
            firmware_version="0.1.0-sim",
            revoked=revoked,
        ),
        SECRET,
    )
    return DeviceMessageVerifier(validator(), registry)


@pytest.mark.parametrize(
    ("profile_name", "revision", "expected_capability"),
    [
        ("cardputer.original.v1.json", "original", "infrared_tx"),
        ("cardputer.adv.v1.json", "adv", "imu"),
    ],
)
def test_official_board_profiles_validate_and_remain_distinct(
    profile_name: str,
    revision: str,
    expected_capability: str,
) -> None:
    payload = load_json(PROFILES / profile_name)
    schema = load_json(SCHEMAS / "board-profile.schema.json")

    Draft202012Validator(schema).validate(payload)
    parsed = load_board_profile(payload, schema)

    assert parsed.hardware_revision == revision
    assert expected_capability in parsed.capabilities
    assert parsed.maximum_message_bytes == 32_768
    assert parsed.microphone_speaker_simultaneous is False


def test_signed_capability_report_matches_provisioned_profile() -> None:
    device = simulator()
    message = device.capability_report_message(
        sent_at=NOW,
        correlation_id="correlation:capability-01",
    )

    verified = verifier().verify(message, received_at=NOW)

    assert verified.device_id == "cardputer:01"
    assert verified.payload_type == "capability_report"
    assert verified.payload["capabilities"] == [
        "ble",
        "display",
        "infrared_tx",
        "keyboard",
        "micro_sd",
        "microphone",
        "speaker",
        "wifi",
    ]


def test_claimed_capability_cannot_exceed_provisioned_profile() -> None:
    device = simulator()
    message = device.capability_report_message(
        sent_at=NOW,
        correlation_id="correlation:capability-01",
    )
    payload = dict(cast(Mapping[str, object], message["payload"]))
    capabilities = cast(list[str], payload["capabilities"])
    payload["capabilities"] = [*capabilities, "nrf24"]
    unsigned = {key: value for key, value in message.items() if key != "authentication"}
    unsigned["payload"] = payload
    forged = sign_envelope(
        unsigned,
        key_id="device-key:01",
        secret=SECRET,
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier().verify(forged, received_at=NOW)

    assert error.value.reason_code == "CAPABILITY_REPORT_MISMATCH"


def test_tampering_is_rejected_before_replay_state_changes() -> None:
    device = simulator()
    message = device.profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )
    tampered = {**message, "correlation_id": "correlation:tampered"}
    receiver = verifier()

    with pytest.raises(DeviceMessageRejectedError) as error:
        receiver.verify(tampered, received_at=NOW)
    valid = receiver.verify(message, received_at=NOW)

    assert error.value.reason_code == "AUTHENTICATION_INVALID"
    assert valid.sequence == 1


def test_message_id_replay_is_rejected() -> None:
    message = simulator().profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )
    receiver = verifier()
    receiver.verify(message, received_at=NOW)

    with pytest.raises(DeviceMessageRejectedError) as error:
        receiver.verify(message, received_at=NOW)

    assert error.value.reason_code == "MESSAGE_ID_REPLAYED"


def test_non_increasing_sequence_is_rejected() -> None:
    device = simulator()
    first = device.profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )
    second = device.profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-02",
    )
    receiver = verifier()
    receiver.verify(second, received_at=NOW)

    with pytest.raises(DeviceMessageRejectedError) as error:
        receiver.verify(first, received_at=NOW)

    assert error.value.reason_code == "SEQUENCE_REPLAYED"


@pytest.mark.parametrize(
    ("received_at", "reason_code"),
    [
        (NOW + timedelta(minutes=6), "MESSAGE_TIMESTAMP_INVALID"),
        (NOW - timedelta(seconds=31), "MESSAGE_TIMESTAMP_INVALID"),
    ],
)
def test_stale_or_future_message_is_rejected(
    received_at: datetime,
    reason_code: str,
) -> None:
    message = simulator().profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier().verify(message, received_at=received_at)

    assert error.value.reason_code == reason_code


def test_revoked_device_is_rejected() -> None:
    message = simulator().profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier(revoked=True).verify(message, received_at=NOW)

    assert error.value.reason_code == "DEVICE_REVOKED"


def test_unknown_device_is_rejected() -> None:
    message = simulator().profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )
    empty_registry = DeviceRegistry()

    with pytest.raises(DeviceMessageRejectedError) as error:
        DeviceMessageVerifier(validator(), empty_registry).verify(
            message,
            received_at=NOW,
        )

    assert error.value.reason_code == "DEVICE_UNKNOWN"


def test_unsupported_protocol_version_has_stable_rejection() -> None:
    message = simulator().profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )
    changed = {**message, "protocol_version": 2}

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier().verify(changed, received_at=NOW)

    assert error.value.reason_code == "PROTOCOL_VERSION_UNSUPPORTED"


def test_oversized_message_is_rejected_before_schema_validation() -> None:
    device = simulator()
    command = {
        "contract_version": 1,
        "command_id": "command:01",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": "assistant",
        "action": "camera.status",
        "targets": ["camera:garage-01"],
        "parameters": {"padding": "x" * 33_000},
        "requested_at": "2026-07-25T18:40:00Z",
    }
    message = device.text_command_message(
        command,
        sent_at=NOW,
        correlation_id="correlation:command-01",
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier().verify(message, received_at=NOW)

    assert error.value.reason_code == "MESSAGE_TOO_LARGE"


def test_lab_profile_requires_unlock_scope_operator_and_short_expiry() -> None:
    device = simulator()

    with pytest.raises(PermissionError):
        device.switch_profile(
            Profile.LAB,
            changed_at=NOW,
            unlocked=True,
        )
    lab = device.switch_profile(
        Profile.LAB,
        changed_at=NOW,
        unlocked=True,
        operator_id="user:01",
        active_scope_id="scope:lab-01",
        expires_at=NOW + timedelta(minutes=10),
    )

    assert lab.indicator == "PROFILE: LAB"
    assert lab.operator_id == "user:01"
    assert lab.scope_id == "scope:lab-01"
    assert device.tick(NOW + timedelta(minutes=10)).active_profile is Profile.ASSISTANT


def test_reboot_resets_visible_profile_to_assistant() -> None:
    device = simulator()
    device.switch_profile(
        Profile.SENTINEL,
        changed_at=NOW,
        unlocked=True,
    )

    state = device.reboot()
    message = device.profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )

    assert state.active_profile is Profile.ASSISTANT
    assert state.indicator == "PROFILE: ASSISTANT"
    Draft202012Validator(
        load_json(SCHEMAS / "profile-state.schema.json"),
        format_checker=FormatChecker(),
    ).validate(message["payload"])


def test_text_command_must_match_visible_profile_before_signing() -> None:
    device = simulator()
    sentinel_command = {
        "contract_version": 1,
        "command_id": "command:monitor-01",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": "sentinel",
        "action": "camera.monitor",
        "targets": ["camera:garage-01"],
        "parameters": {"duration_seconds": 120},
        "requested_at": "2026-07-25T18:40:00Z",
    }

    with pytest.raises(PermissionError, match="visible active profile"):
        device.text_command_message(
            sentinel_command,
            sent_at=NOW,
            correlation_id="correlation:command-01",
        )
    device.switch_profile(
        Profile.SENTINEL,
        changed_at=NOW,
        unlocked=True,
    )
    message = device.text_command_message(
        sentinel_command,
        sent_at=NOW,
        correlation_id="correlation:command-01",
    )

    verified = verifier().verify(message, received_at=NOW)
    assert verified.payload_type == "text_command"


def test_push_to_talk_requires_press_and_has_visible_state() -> None:
    recorder = PushToTalkRecorder(board())

    with pytest.raises(RuntimeError, match="not recording"):
        recorder.append_encoded(b"not-background-audio", duration_ms=100)
    recorder.press("capture:01", recorded_at=NOW)
    recorder.append_encoded(b"simulated-opus-frame", duration_ms=800)
    metadata = recorder.release(completed_at=NOW + timedelta(milliseconds=800))

    assert recorder.indicator == "MIC: READY"
    assert recorder.state is AudioCaptureState.READY
    assert metadata.duration_ms == 800
    assert metadata.byte_length == len(b"simulated-opus-frame")


def test_push_to_talk_requires_trusted_microphone_capability() -> None:
    profile = board()
    without_microphone = BoardProfile(
        board_profile_id=profile.board_profile_id,
        hardware_revision=profile.hardware_revision,
        controller=profile.controller,
        capabilities=profile.capabilities - {"microphone"},
        maximum_message_bytes=profile.maximum_message_bytes,
        microphone_speaker_simultaneous=profile.microphone_speaker_simultaneous,
    )

    with pytest.raises(ValueError, match="trusted microphone"):
        PushToTalkRecorder(without_microphone)


@pytest.mark.parametrize(
    ("chunk", "duration_ms"),
    [
        (b"x" * (MAXIMUM_ENCODED_AUDIO_BYTES + 1), 1),
        (b"x", MAXIMUM_CAPTURE_DURATION_MS + 1),
    ],
)
def test_push_to_talk_limit_violation_cancels_and_clears(
    chunk: bytes,
    duration_ms: int,
) -> None:
    recorder = PushToTalkRecorder(board())
    recorder.press("capture:limit-01", recorded_at=NOW)

    with pytest.raises(AudioCaptureLimitError):
        recorder.append_encoded(chunk, duration_ms=duration_ms)

    assert recorder.state is AudioCaptureState.CANCELLED
    assert recorder.indicator == "MIC: LIMIT REACHED"
    assert recorder.buffered_bytes == 0


def test_push_to_talk_physical_cancel_clears_buffer() -> None:
    recorder = PushToTalkRecorder(board())
    recorder.press("capture:cancel-01", recorded_at=NOW)
    recorder.append_encoded(b"personal-audio-fixture", duration_ms=500)

    recorder.cancel()

    assert recorder.state is AudioCaptureState.CANCELLED
    assert recorder.indicator == "MIC: CANCELLED"
    assert recorder.buffered_bytes == 0


def test_maximum_push_to_talk_capture_fits_protocol_envelope() -> None:
    device = simulator()
    recorder = PushToTalkRecorder(device.board_profile)
    recorder.press("capture:maximum-01", recorded_at=NOW)
    recorder.append_encoded(
        b"x" * MAXIMUM_ENCODED_AUDIO_BYTES,
        duration_ms=MAXIMUM_CAPTURE_DURATION_MS,
    )
    recorder.release(completed_at=NOW + timedelta(seconds=15))

    message = device.voice_command_message(
        recorder,
        sent_at=NOW + timedelta(seconds=16),
        correlation_id="correlation:maximum-01",
    )
    verified = verifier().verify(
        message,
        received_at=NOW + timedelta(seconds=16),
    )

    assert verified.payload_type == "voice_command"
    assert len(json.dumps(message).encode()) < 32_768


def test_signed_voice_command_is_bounded_validated_and_deleted_after_success() -> None:
    device = simulator()
    recorder = PushToTalkRecorder(device.board_profile)
    recorder.press("capture:voice-01", recorded_at=NOW)
    recorder.append_encoded(b"simulated-opus-frame", duration_ms=800)
    recorder.release(completed_at=NOW + timedelta(milliseconds=800))
    message = device.voice_command_message(
        recorder,
        sent_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:voice-01",
    )

    verified = verifier().verify(
        message,
        received_at=NOW + timedelta(seconds=1),
    )
    audio = cast(Mapping[str, object], verified.payload["audio"])

    assert verified.payload_type == "voice_command"
    assert audio["byte_length"] == len(b"simulated-opus-frame")
    assert len(json.dumps(message).encode()) < 32_768
    recorder.acknowledge_processed("capture:voice-01", succeeded=True)
    assert recorder.state is AudioCaptureState.IDLE
    assert recorder.buffered_bytes == 0


def test_failed_processing_keeps_capture_for_bounded_retry() -> None:
    recorder = PushToTalkRecorder(board())
    recorder.press("capture:retry-01", recorded_at=NOW)
    recorder.append_encoded(b"simulated-opus-frame", duration_ms=800)
    recorder.release(completed_at=NOW + timedelta(milliseconds=800))

    recorder.acknowledge_processed("capture:retry-01", succeeded=False)

    assert recorder.state is AudioCaptureState.READY
    assert recorder.buffered_bytes == len(b"simulated-opus-frame")


def test_voice_payload_with_forged_length_is_rejected() -> None:
    device = simulator()
    recorder = PushToTalkRecorder(device.board_profile)
    recorder.press("capture:voice-01", recorded_at=NOW)
    recorder.append_encoded(b"simulated-opus-frame", duration_ms=800)
    recorder.release(completed_at=NOW + timedelta(milliseconds=800))
    message = device.voice_command_message(
        recorder,
        sent_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:voice-01",
    )
    payload = dict(cast(Mapping[str, object], message["payload"]))
    audio = dict(cast(Mapping[str, object], payload["audio"]))
    audio["byte_length"] = cast(int, audio["byte_length"]) + 1
    payload["audio"] = audio
    unsigned = {key: value for key, value in message.items() if key != "authentication"}
    unsigned["payload"] = payload
    forged = sign_envelope(
        unsigned,
        key_id="device-key:01",
        secret=SECRET,
    )

    with pytest.raises(DeviceMessageRejectedError) as error:
        verifier().verify(forged, received_at=NOW + timedelta(seconds=1))

    assert error.value.reason_code == "AUDIO_LENGTH_MISMATCH"

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


@pytest.mark.parametrize("schema_path", sorted(SCHEMAS.glob("*.schema.json")))
def test_schema_is_valid_draft_2020_12(schema_path: Path) -> None:
    Draft202012Validator.check_schema(load_json(schema_path))


@pytest.mark.parametrize(
    "manifest_name",
    [
        "asset.list.v1.json",
        "camera.monitor.v1.json",
        "camera.status.v1.json",
        "network.passive_discovery.v1.json",
    ],
)
def test_camera_manifest_matches_contract(manifest_name: str) -> None:
    schema = load_json(SCHEMAS / "tool-manifest.schema.json")
    manifest = load_json(ROOT / "config" / "tools" / manifest_name)

    Draft202012Validator(schema).validate(manifest)
    Draft202012Validator.check_schema(manifest["parameters_schema"])
    Draft202012Validator.check_schema(manifest["result_schema"])


def test_audit_event_rejects_secret_or_extra_fields() -> None:
    schema = load_json(SCHEMAS / "audit-event.schema.json")
    event = {
        "contract_version": 1,
        "event_id": "audit:01",
        "timestamp": "2026-07-25T18:40:01Z",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "device_id": "cardputer:01",
        "profile": "assistant",
        "scope_id": None,
        "tool_id": "camera.status",
        "tool_version": 1,
        "targets": ["camera:garage-01"],
        "parameters_hash": f"sha256:{'a' * 64}",
        "plan_hash": f"sha256:{'b' * 64}",
        "policy_decision": "allow",
        "reason_code": "AUTHORIZED",
        "confirmation_method": None,
        "result": "simulated",
        "correlation_id": "correlation:01",
        "private_stream_url": "rtsp://secret.invalid/private",
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(event)


def test_tool_contract_cannot_expose_r3() -> None:
    schema = load_json(SCHEMAS / "tool-manifest.schema.json")
    manifest = load_json(ROOT / "config" / "tools" / "camera.monitor.v1.json")
    manifest["risk_class"] = "R3"

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_command_rejects_unknown_fields() -> None:
    schema = load_json(SCHEMAS / "command.schema.json")
    command = {
        "contract_version": 1,
        "command_id": "command:01",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": "sentinel",
        "action": "camera.monitor",
        "targets": ["camera:garage-01"],
        "parameters": {"duration_seconds": 120},
        "requested_at": "2026-07-25T18:40:01Z",
        "free_form_shell": "do something unsafe",
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(command)


def test_command_rejects_untyped_target() -> None:
    schema = load_json(SCHEMAS / "command.schema.json")
    command = {
        "contract_version": 1,
        "command_id": "command:01",
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": "sentinel",
        "action": "camera.monitor",
        "targets": ["garage-01"],
        "parameters": {"duration_seconds": 120},
        "requested_at": "2026-07-25T18:40:01Z",
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(command)


def test_device_identity_status_accepts_non_secret_simulation_receipt() -> None:
    schema = load_json(SCHEMAS / "device-identity-status.schema.json")
    status = {
        "contract_version": 1,
        "device_id": "cardputer:01",
        "key_id": "device-key:02",
        "board_profile_id": "board-profile:cardputer-original-v1",
        "firmware_version": "0.2.2-poc",
        "identity_revision": 2,
        "state": "trusted",
        "execution_mode": "simulation",
    }

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(status)


@pytest.mark.parametrize("secret_field", ["secret", "token", "private_key"])
def test_device_identity_status_rejects_secret_fields(secret_field: str) -> None:
    schema = load_json(SCHEMAS / "device-identity-status.schema.json")
    status = {
        "contract_version": 1,
        "device_id": "cardputer:01",
        "key_id": "device-key:02",
        "board_profile_id": "board-profile:cardputer-original-v1",
        "firmware_version": "0.2.2-poc",
        "identity_revision": 2,
        "state": "trusted",
        "execution_mode": "simulation",
        secret_field: "must-not-cross-this-contract",
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(status)


def test_voice_command_contract_accepts_bounded_capture() -> None:
    schema = load_json(SCHEMAS / "voice-command.schema.json")
    payload = {
        "contract_version": 1,
        "capture_id": "capture:01",
        "active_profile": "sentinel",
        "recorded_at": "2026-07-25T18:40:00Z",
        "completed_at": "2026-07-25T18:40:01Z",
        "audio": {
            "encoding": "opus",
            "sample_rate": 16_000,
            "channels": 1,
            "duration_ms": 800,
            "byte_length": 4,
            "content_base64": "dGVzdA==",
        },
        "retention": "delete_after_processing",
    }

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_ms", 15_001),
        ("byte_length", 18_001),
        ("content_base64", "not base64"),
    ],
)
def test_voice_command_contract_rejects_unbounded_or_invalid_audio(
    field: str,
    value: int | str,
) -> None:
    schema = load_json(SCHEMAS / "voice-command.schema.json")
    payload = {
        "contract_version": 1,
        "capture_id": "capture:01",
        "active_profile": "sentinel",
        "recorded_at": "2026-07-25T18:40:00Z",
        "completed_at": "2026-07-25T18:40:01Z",
        "audio": {
            "encoding": "opus",
            "sample_rate": 16_000,
            "channels": 1,
            "duration_ms": 800,
            "byte_length": 4,
            "content_base64": "dGVzdA==",
        },
        "retention": "delete_after_processing",
    }
    payload["audio"][field] = value

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(payload)


def test_speech_transcription_contract_accepts_normalized_text_only() -> None:
    schema = load_json(SCHEMAS / "speech-transcription.schema.json")
    payload = {
        "contract_version": 1,
        "transcription_id": "transcription:01",
        "provider_id": "speech-provider:fixture-v1",
        "execution_mode": "simulated",
        "language": "pt-BR",
        "text": "Monitore a câmera da garagem por dois minutos.",
        "audio_sha256": f"sha256:{'a' * 64}",
        "created_at": "2026-07-25T18:40:02Z",
    }

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", "speech-provider:unknown"),
        ("execution_mode", "real"),
        ("language", "auto"),
        ("text", ""),
        ("audio_sha256", "sha256:invalid"),
        ("raw_audio", "must-not-cross-this-contract"),
    ],
)
def test_speech_transcription_contract_rejects_invalid_or_raw_provider_output(
    field: str,
    value: str,
) -> None:
    schema = load_json(SCHEMAS / "speech-transcription.schema.json")
    payload = {
        "contract_version": 1,
        "transcription_id": "transcription:01",
        "provider_id": "speech-provider:fixture-v1",
        "execution_mode": "simulated",
        "language": "pt-BR",
        "text": "Monitore a câmera da garagem por dois minutos.",
        "audio_sha256": f"sha256:{'a' * 64}",
        "created_at": "2026-07-25T18:40:02Z",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(payload)


def test_policy_request_matches_contract() -> None:
    schema = load_json(SCHEMAS / "policy-request.schema.json")
    request = {
        "contract_version": 1,
        "actor": {
            "actor_id": "user:01",
            "organization_id": "org:01",
            "roles": ["operator"],
        },
        "device": {
            "device_id": "cardputer:01",
            "organization_id": "org:01",
            "trust_state": "trusted",
            "capabilities": ["camera_monitoring"],
        },
        "profile": "sentinel",
        "tool_id": "camera.monitor",
        "tool_version": 1,
        "targets": ["camera:garage-01"],
        "parameters": {"duration_seconds": 120},
        "evaluated_at": "2026-07-25T18:40:01Z",
        "plan_hash": f"sha256:{'a' * 64}",
        "resource_grant": {
            "organization_id": "org:01",
            "resource_ids": ["camera:garage-01"],
            "valid_until": "2026-07-25T18:45:01Z",
        },
        "operation_scope": None,
        "confirmation": None,
    }

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(request)

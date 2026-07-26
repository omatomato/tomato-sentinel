import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_orchestrator import (
    CameraRecord,
    CameraState,
    CameraStatusService,
    CommandRejectedError,
    ContractValidator,
    ExecutionContext,
    ExecutionStatus,
    InMemoryAuditSink,
    InMemoryCameraRepository,
    audit_to_contract,
    camera_status_manifest,
    outcome_to_contract,
)
from tomato_sentinel_policy import (
    ActorContext,
    DeviceContext,
    ResourceGrant,
    ToolRegistry,
    TrustState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
NOW = datetime(2026, 7, 25, 18, 40, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def command(
    *,
    command_id: str = "command:status-01",
    action: str = "camera.status",
    targets: list[str] | None = None,
    parameters: dict[str, object] | None = None,
    profile: str = "assistant",
    requested_at: str = "2026-07-25T18:40:00Z",
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": command_id,
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": profile,
        "action": action,
        "targets": targets or ["camera:garage-01"],
        "parameters": parameters or {},
        "requested_at": requested_at,
        "correlation_id": "correlation:status-01",
    }


def context() -> ExecutionContext:
    return ExecutionContext(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"viewer"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"camera_status_query"}),
        ),
        resource_grant=ResourceGrant(
            organization_id="org:01",
            resource_ids=frozenset(
                {"camera:garage-01", "camera:entrance-01", "camera:other-01"}
            ),
            valid_until=NOW + timedelta(minutes=10),
        ),
    )


def cameras() -> InMemoryCameraRepository:
    return InMemoryCameraRepository(
        (
            CameraRecord(
                camera_id="camera:garage-01",
                organization_id="org:01",
                display_name="Garage",
                status=CameraState.OFFLINE,
                observed_at=NOW - timedelta(seconds=30),
                credential_reference="vault:camera-garage",
                private_stream_url="rtsp://admin:secret@192.0.2.10/private",
            ),
            CameraRecord(
                camera_id="camera:entrance-01",
                organization_id="org:01",
                display_name="Entrance",
                status=CameraState.ONLINE,
                observed_at=NOW - timedelta(seconds=5),
                credential_reference="vault:camera-entrance",
                private_stream_url="rtsp://private.example/entrance",
            ),
            CameraRecord(
                camera_id="camera:other-01",
                organization_id="org:other",
                display_name="Other tenant",
                status=CameraState.ONLINE,
                observed_at=NOW,
                credential_reference="vault:other",
                private_stream_url="rtsp://other.example/private",
            ),
        )
    )


def build_service() -> tuple[CameraStatusService, InMemoryAuditSink]:
    validator = ContractValidator(
        load_json(SCHEMAS / "command.schema.json"),
        (load_json(ROOT / "config" / "tools" / "camera.status.v1.json"),),
    )
    registry = ToolRegistry()
    registry.register(camera_status_manifest())
    audit = InMemoryAuditSink()
    return CameraStatusService(validator, registry, cameras(), audit), audit


def test_authorized_status_query_returns_only_sanitized_state() -> None:
    service, audit = build_service()
    payload = command(targets=["camera:garage-01", "camera:entrance-01"])

    outcome = service.execute(payload, context(), evaluated_at=NOW)
    result = outcome_to_contract(outcome)
    audit_contract = audit_to_contract(audit.events[0])

    assert outcome.status is ExecutionStatus.SIMULATED
    assert [camera.status for camera in outcome.cameras] == [
        CameraState.OFFLINE,
        CameraState.ONLINE,
    ]
    assert len(audit.events) == 1
    Draft202012Validator(
        load_json(ROOT / "config" / "tools" / "camera.status.v1.json")["result_schema"],
        format_checker=FormatChecker(),
    ).validate(result)
    Draft202012Validator(
        load_json(SCHEMAS / "audit-event.schema.json"),
        format_checker=FormatChecker(),
    ).validate(audit_contract)

    serialized = json.dumps({"result": result, "audit": audit_contract})
    assert "secret" not in serialized
    assert "rtsp://" not in serialized
    assert "vault:" not in serialized


def test_domain_manifest_matches_the_registered_contract() -> None:
    contract = load_json(ROOT / "config" / "tools" / "camera.status.v1.json")
    manifest = camera_status_manifest()

    assert manifest.tool_id == contract["tool_id"]
    assert manifest.version == contract["version"]
    assert manifest.risk_class.value == contract["risk_class"]
    assert manifest.required_profile.value == contract["required_profile"]
    assert manifest.authorization_kind.value == contract["authorization_kind"]
    assert sorted(manifest.required_roles) == contract["required_roles"]
    assert sorted(manifest.required_capabilities) == contract["required_capabilities"]
    assert manifest.requires_confirmation == contract["requires_confirmation"]
    assert (
        manifest.requires_physical_confirmation
        == contract["requires_physical_confirmation"]
    )
    assert manifest.maximum_targets == contract["maximum_targets"]


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    [
        (command(action="camera.unknown"), "ACTION_NOT_REGISTERED"),
        (
            command(parameters={"include_private_stream_url": True}),
            "PARAMETERS_SCHEMA_INVALID",
        ),
        (
            {**command(), "free_form_shell": "cat /etc/passwd"},
            "COMMAND_SCHEMA_INVALID",
        ),
    ],
)
def test_invalid_command_is_rejected_before_audit(
    payload: dict[str, object],
    reason_code: str,
) -> None:
    service, audit = build_service()

    with pytest.raises(CommandRejectedError) as error:
        service.execute(payload, context(), evaluated_at=NOW)

    assert error.value.reason_code == reason_code
    assert audit.events == ()


def test_oversized_command_is_rejected_before_schema_processing() -> None:
    service, audit = build_service()
    payload = command(parameters={"padding": "x" * 17_000})

    with pytest.raises(CommandRejectedError) as error:
        service.execute(payload, context(), evaluated_at=NOW)

    assert error.value.reason_code == "COMMAND_TOO_LARGE"
    assert audit.events == ()


@pytest.mark.parametrize(
    "requested_at",
    ["2026-07-25T18:34:59Z", "2026-07-25T18:40:31Z"],
)
def test_stale_or_future_command_is_denied_and_audited(
    requested_at: str,
) -> None:
    service, audit = build_service()

    outcome = service.execute(
        command(requested_at=requested_at),
        context(),
        evaluated_at=NOW,
    )

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == "COMMAND_TIMESTAMP_INVALID"
    assert audit.events[0].reason_code == "COMMAND_TIMESTAMP_INVALID"


def test_cross_tenant_camera_is_indistinguishable_from_missing_camera() -> None:
    service, audit = build_service()

    cross_tenant = service.execute(
        command(targets=["camera:other-01"]),
        context(),
        evaluated_at=NOW,
    )

    assert cross_tenant.status is ExecutionStatus.DENIED
    assert cross_tenant.reason_code == "TARGET_NOT_ACCESSIBLE"
    assert cross_tenant.cameras == ()
    assert audit.events[0].result is ExecutionStatus.DENIED


def test_policy_denial_starts_no_query_result() -> None:
    service, audit = build_service()
    unauthorized_context = replace(
        context(),
        resource_grant=replace(
            context().resource_grant,
            resource_ids=frozenset(),
        ),
    )

    outcome = service.execute(
        command(),
        unauthorized_context,
        evaluated_at=NOW,
    )

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == "TARGET_NOT_AUTHORIZED"
    assert outcome.cameras == ()
    assert audit.events[0].policy_decision == "deny"


@pytest.mark.parametrize(
    ("changed_context", "reason_code"),
    [
        (
            replace(
                context(),
                device=replace(
                    context().device,
                    trust_state=TrustState.REVOKED,
                ),
            ),
            "DEVICE_NOT_TRUSTED",
        ),
        (
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    valid_until=NOW,
                ),
            ),
            "GRANT_EXPIRED",
        ),
    ],
)
def test_security_context_denials_are_audited(
    changed_context: ExecutionContext,
    reason_code: str,
) -> None:
    service, audit = build_service()

    outcome = service.execute(command(), changed_context, evaluated_at=NOW)

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == reason_code
    assert audit.events[0].reason_code == reason_code


def test_command_identity_must_match_authenticated_context() -> None:
    service, audit = build_service()
    payload = {**command(), "actor_id": "user:spoofed"}

    outcome = service.execute(payload, context(), evaluated_at=NOW)

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == "COMMAND_CONTEXT_MISMATCH"
    assert audit.events[0].actor_id == "user:01"


def test_identical_command_replay_has_one_audit_side_effect() -> None:
    service, audit = build_service()
    payload = command()

    first = service.execute(payload, context(), evaluated_at=NOW)
    replay = service.execute(
        payload,
        context(),
        evaluated_at=NOW + timedelta(seconds=5),
    )

    assert replay == first
    assert len(audit.events) == 1


def test_changed_payload_cannot_reuse_command_identifier() -> None:
    service, audit = build_service()
    service.execute(command(), context(), evaluated_at=NOW)

    with pytest.raises(CommandRejectedError) as error:
        service.execute(
            command(targets=["camera:entrance-01"]),
            context(),
            evaluated_at=NOW,
        )

    assert error.value.reason_code == "IDEMPOTENCY_KEY_REUSED"
    assert len(audit.events) == 1


def test_wrong_profile_is_denied_by_shared_policy() -> None:
    service, audit = build_service()

    outcome = service.execute(
        command(profile="sentinel"),
        context(),
        evaluated_at=NOW,
    )

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == "PROFILE_REQUIRED"
    assert audit.events[0].policy_decision == "require_profile_change"

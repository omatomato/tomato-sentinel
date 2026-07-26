import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_device_protocol import (
    CardputerSimulator,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    ProvisionedDevice,
    load_board_profile,
)
from tomato_sentinel_orchestrator import (
    ContractValidator,
    DeviceCancelGateway,
    DiscoveryCandidate,
    ExecutionContext,
    ExecutionStatus,
    InMemoryAuditSink,
    InMemoryPassiveDiscoverySource,
    JobState,
    MonitoringService,
    PassiveDiscoveryService,
    audit_to_contract,
    discovery_candidate_to_contract,
    discovery_outcome_to_contract,
    passive_discovery_manifest,
    transition_to_contract,
)
from tomato_sentinel_policy import (
    ActorContext,
    DeviceContext,
    OperationScope,
    ResourceGrant,
    ToolRegistry,
    TrustState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
MANIFEST = ROOT / "config" / "tools" / "network.passive_discovery.v1.json"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)
SECRET = b"passive-discovery-cancel-simulation-key"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def command(
    *,
    command_id: str = "command:passive-discovery-01",
    target: str = "network:lab",
    profile: str = "inventory",
    duration_seconds: int = 30,
    interface_id: str = "interface:edge-lan",
    maximum_candidates: int = 32,
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": command_id,
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": profile,
        "action": "network.passive_discovery",
        "targets": [target],
        "parameters": {
            "duration_seconds": duration_seconds,
            "interface_id": interface_id,
            "maximum_candidates": maximum_candidates,
        },
        "requested_at": "2026-07-26T23:00:00Z",
        "correlation_id": "correlation:passive-discovery-01",
    }


def context(
    *,
    scope: OperationScope | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"inventory_operator"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"passive_network_observation"}),
        ),
        resource_grant=ResourceGrant(
            organization_id="org:01",
            resource_ids=frozenset({"inventory:primary"}),
            valid_until=NOW + timedelta(minutes=10),
        ),
        operation_scope=scope or operation_scope(),
    )


def operation_scope() -> OperationScope:
    return OperationScope(
        scope_id="scope:passive-discovery-01",
        organization_id="org:01",
        tool_ids=frozenset({"network.passive_discovery"}),
        target_ids=frozenset({"network:lab"}),
        valid_until=NOW + timedelta(minutes=5),
    )


def candidates() -> tuple[DiscoveryCandidate, ...]:
    return (
        DiscoveryCandidate(
            candidate_id="candidate:camera-pseudonym",
            organization_id="org:01",
            observer_id="edge:lab-01",
            network_id="network:lab",
            interface_id="interface:edge-lan",
            protocols=("dhcp_lease", "mdns_announcement"),
            probable_types=("camera",),
            authentication_required=True,
            first_observed_at=NOW - timedelta(minutes=1),
            last_observed_at=NOW,
            confidence=0.91,
        ),
        DiscoveryCandidate(
            candidate_id="candidate:unknown-pseudonym",
            organization_id="org:01",
            observer_id="edge:lab-01",
            network_id="network:lab",
            interface_id="interface:edge-lan",
            protocols=("arp_cache",),
            probable_types=("unknown",),
            authentication_required=None,
            first_observed_at=NOW,
            last_observed_at=NOW,
            confidence=0.4,
        ),
    )


def build_service(
    fixture: tuple[DiscoveryCandidate, ...] | None = None,
) -> tuple[
    PassiveDiscoveryService,
    InMemoryPassiveDiscoverySource,
    InMemoryAuditSink,
]:
    registry = ToolRegistry()
    registry.register(passive_discovery_manifest())
    source = InMemoryPassiveDiscoverySource(
        {
            ("org:01", "network:lab", "interface:edge-lan"): (
                candidates() if fixture is None else fixture
            )
        }
    )
    audit = InMemoryAuditSink()
    return (
        PassiveDiscoveryService(
            validator=ContractValidator(
                load_json(SCHEMAS / "command.schema.json"),
                (load_json(MANIFEST),),
            ),
            registry=registry,
            source=source,
            audit=audit,
        ),
        source,
        audit,
    )


@pytest.mark.parametrize(
    "invalid_candidate",
    [
        replace(candidates()[0], protocols=("active_port_scan",)),
        replace(candidates()[0], confidence=cast(float, True)),
        replace(candidates()[0], candidate_id="asset:not-a-candidate"),
    ],
)
def test_fake_adapter_rejects_invalid_candidate_output(
    invalid_candidate: DiscoveryCandidate,
) -> None:
    with pytest.raises(ValueError):
        InMemoryPassiveDiscoverySource(
            {
                (
                    "org:01",
                    "network:lab",
                    "interface:edge-lan",
                ): (invalid_candidate,)
            }
        )


def test_passive_discovery_completes_with_untrusted_sanitized_candidates() -> None:
    service, source, audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)

    completed = service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )
    public = discovery_outcome_to_contract(completed)
    serialized = json.dumps(public)

    assert started.status is JobState.RUNNING
    assert completed.status is JobState.COMPLETED
    assert len(completed.candidates) == 2
    assert source.worker_starts == 1
    assert "organization_id" not in serialized
    assert "asset_id" not in serialized
    assert "mac" not in serialized.lower()
    public_candidates = cast(list[dict[str, object]], public["candidates"])
    assert all(
        candidate["enrollment_status"] == "candidate" for candidate in public_candidates
    )
    Draft202012Validator(
        load_json(MANIFEST)["result_schema"],
        format_checker=FormatChecker(),
    ).validate(public)
    for candidate in completed.candidates:
        Draft202012Validator(
            load_json(SCHEMAS / "discovery-candidate.schema.json"),
            format_checker=FormatChecker(),
        ).validate(discovery_candidate_to_contract(candidate))
    for transition in service.jobs[0].transitions:
        Draft202012Validator(
            load_json(SCHEMAS / "job-transition.schema.json"),
            format_checker=FormatChecker(),
        ).validate(transition_to_contract(transition))
    audit_contract = audit_to_contract(audit.events[0])
    assert audit_contract["scope_id"] == "scope:passive-discovery-01"


@pytest.mark.parametrize(
    ("changed_context", "payload", "reason_code"),
    [
        (
            replace(context(), operation_scope=None),
            command(),
            "SCOPE_REQUIRED",
        ),
        (
            context(
                scope=replace(
                    operation_scope(),
                    valid_until=NOW,
                )
            ),
            command(),
            "SCOPE_EXPIRED",
        ),
        (
            context(
                scope=replace(
                    operation_scope(),
                    target_ids=frozenset({"network:other"}),
                )
            ),
            command(),
            "TARGET_NOT_AUTHORIZED",
        ),
        (context(), command(profile="assistant"), "PROFILE_REQUIRED"),
        (
            replace(
                context(),
                device=replace(
                    context().device,
                    capabilities=frozenset(),
                ),
            ),
            command(),
            "CAPABILITY_REQUIRED",
        ),
    ],
)
def test_discovery_policy_denials_start_no_worker(
    changed_context: ExecutionContext,
    payload: dict[str, object],
    reason_code: str,
) -> None:
    service, source, audit = build_service()

    outcome = service.start(payload, changed_context, evaluated_at=NOW)

    assert outcome.status is JobState.DENIED
    assert outcome.candidates == ()
    assert outcome.reason_code == reason_code
    assert source.worker_starts == 0
    assert audit.events[0].result is ExecutionStatus.DENIED


def test_scope_must_cover_the_complete_discovery_duration() -> None:
    service, source, _audit = build_service()
    short_scope = replace(
        operation_scope(),
        valid_until=NOW + timedelta(seconds=10),
    )

    outcome = service.start(
        command(duration_seconds=30),
        context(scope=short_scope),
        evaluated_at=NOW,
    )

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == "SCOPE_EXPIRES_BEFORE_JOB"
    assert source.worker_starts == 0


def test_unconfigured_interface_is_denied_without_starting_worker() -> None:
    service, source, _audit = build_service()

    outcome = service.start(
        command(interface_id="interface:unconfigured"),
        context(),
        evaluated_at=NOW,
    )

    assert outcome.status is JobState.DENIED
    assert outcome.reason_code == "DISCOVERY_SOURCE_NOT_CONFIGURED"
    assert source.worker_starts == 0


def test_discovery_limit_and_command_replay_are_bounded_and_idempotent() -> None:
    service, source, audit = build_service()
    payload = command(maximum_candidates=1)

    started = service.start(payload, context(), evaluated_at=NOW)
    replay = service.start(
        payload,
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )
    completed = service.run_to_completion(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )

    assert replay.job_id == started.job_id
    assert len(completed.candidates) == 1
    assert source.worker_starts == 1
    assert len(audit.events) == 1


def test_discovery_cancellation_is_idempotent_and_context_bound() -> None:
    service, source, audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)

    cancelled = service.cancel(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )
    replay = service.cancel(
        started.job_id or "",
        context(),
        evaluated_at=NOW + timedelta(seconds=2),
    )
    wrong_context = replace(
        context(),
        actor=replace(context().actor, actor_id="user:other"),
    )

    with pytest.raises(PermissionError):
        service.cancel(
            started.job_id or "",
            wrong_context,
            evaluated_at=NOW + timedelta(seconds=3),
        )

    assert cancelled.status is JobState.CANCELLED
    assert replay == cancelled
    assert source.next_candidate(started.job_id or "") is None
    assert len(audit.events) == 1


def test_signed_physical_cancel_routes_to_exact_discovery_job() -> None:
    service, _source, audit = build_service()
    started = service.start(command(), context(), evaluated_at=NOW)
    board = load_board_profile(
        load_json(PROFILES / "cardputer.original.v1.json"),
        load_json(SCHEMAS / "board-profile.schema.json"),
    )
    device = CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=SECRET,
        board_profile=board,
        firmware_version="0.2.2-sim",
        boot_id="boot:discovery-cancel-01",
    )
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board,
            firmware_version="0.2.2-sim",
        ),
        SECRET,
    )
    gateway = DeviceCancelGateway(
        DeviceMessageVerifier(
            DeviceProtocolValidator(
                envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
                payload_schemas={
                    "cancel_request": load_json(SCHEMAS / "cancel-request.schema.json")
                },
            ),
            registry,
        )
    )
    envelope = device.physical_cancel_message(
        started.job_id or "",
        sent_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:discovery-cancel-01",
    )

    cancelled = gateway.handle(
        envelope,
        context(),
        cast(MonitoringService, object()),
        received_at=NOW + timedelta(seconds=1),
        discovery=service,
    )

    assert cancelled.status is JobState.CANCELLED
    assert audit.events[0].result is ExecutionStatus.CANCELLED

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tomato_sentinel_device_protocol import (
    CardputerSimulator,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    InventoryMenuEntry,
    NetworkMenuEntry,
    ProvisionedDevice,
    RegisteredCommandComposer,
    load_board_profile,
)
from tomato_sentinel_orchestrator import (
    AssetChangeState,
    AssetInventoryOutcome,
    AssetInventoryService,
    AssetRecord,
    AssetType,
    CameraRecord,
    CameraState,
    CameraStatusService,
    CommandRejectedError,
    ContractValidator,
    DeviceTextCommandGateway,
    DeviceTextCommandRejectedError,
    ExecutionContext,
    ExecutionStatus,
    InMemoryAssetRepository,
    InMemoryAuditSink,
    InMemoryCameraRepository,
    InMemoryEventSink,
    InMemoryFrameSource,
    InMemoryNotificationSink,
    InMemoryPassiveDiscoverySource,
    JobState,
    MonitoringService,
    NotificationChannel,
    PassiveDiscoveryService,
    asset_list_manifest,
    camera_monitor_manifest,
    camera_status_manifest,
    passive_discovery_manifest,
)
from tomato_sentinel_policy import (
    ActorContext,
    DeviceContext,
    OperationScope,
    Profile,
    ResourceGrant,
    ToolRegistry,
    TrustState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
TOOLS = ROOT / "config" / "tools"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 26, 20, 0, tzinfo=UTC)
SECRET = b"device-text-gateway-simulation-secret"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def command(
    *,
    action: str = "camera.status",
    profile: str = "assistant",
    command_id: str = "command:text-status-01",
    source_device_id: str = "cardputer:01",
    actor_id: str = "user:01",
    requested_at: datetime = NOW,
    correlation_id: str = "correlation:text-status-01",
    target: str = "camera:garage-01",
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": command_id,
        "actor_id": actor_id,
        "organization_id": "org:01",
        "source_device_id": source_device_id,
        "profile": profile,
        "action": action,
        "targets": [target],
        "parameters": (
            {"duration_seconds": 120}
            if action == "camera.monitor" and parameters is None
            else parameters or {}
        ),
        "requested_at": timestamp(requested_at),
        "correlation_id": correlation_id,
    }


def execution_context() -> ExecutionContext:
    return ExecutionContext(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset(
                {"inventory_operator", "inventory_viewer", "operator", "viewer"}
            ),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset(
                {
                    "asset_inventory_query",
                    "camera_monitoring",
                    "camera_status_query",
                    "passive_network_observation",
                }
            ),
        ),
        resource_grant=ResourceGrant(
            organization_id="org:01",
            resource_ids=frozenset(
                {
                    "camera:garage-01",
                    "camera:entrance-01",
                    "inventory:primary",
                }
            ),
            valid_until=NOW + timedelta(minutes=10),
        ),
    )


def build_stack() -> tuple[
    CardputerSimulator,
    DeviceTextCommandGateway,
    InMemoryFrameSource,
    InMemoryAuditSink,
    PassiveDiscoveryService,
]:
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
        boot_id="boot:text-gateway-01",
    )
    device_registry = DeviceRegistry()
    device_registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board,
            firmware_version="0.2.2-sim",
        ),
        SECRET,
    )
    protocol_validator = DeviceProtocolValidator(
        envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
        payload_schemas={
            "text_command": load_json(SCHEMAS / "command.schema.json"),
            "profile_state": load_json(SCHEMAS / "profile-state.schema.json"),
        },
    )

    cameras = InMemoryCameraRepository(
        (
            CameraRecord(
                camera_id="camera:garage-01",
                organization_id="org:01",
                display_name="Garage",
                status=CameraState.ONLINE,
                observed_at=NOW,
                credential_reference="vault:camera-garage",
                private_stream_url="rtsp://private.invalid/garage",
            ),
            CameraRecord(
                camera_id="camera:entrance-01",
                organization_id="org:01",
                display_name="Entrance",
                status=CameraState.ONLINE,
                observed_at=NOW,
                credential_reference="vault:camera-entrance",
                private_stream_url="rtsp://private.invalid/entrance",
            ),
        )
    )
    tools = ToolRegistry()
    tools.register(camera_status_manifest())
    tools.register(camera_monitor_manifest())
    tools.register(asset_list_manifest())
    tools.register(passive_discovery_manifest())
    audit = InMemoryAuditSink()
    status = CameraStatusService(
        ContractValidator(
            load_json(SCHEMAS / "command.schema.json"),
            (load_json(TOOLS / "camera.status.v1.json"),),
        ),
        tools,
        cameras,
        audit,
    )
    frames = InMemoryFrameSource({"camera:garage-01": ()})
    monitoring = MonitoringService(
        validator=ContractValidator(
            load_json(SCHEMAS / "command.schema.json"),
            (load_json(TOOLS / "camera.monitor.v1.json"),),
        ),
        registry=tools,
        cameras=cameras,
        frames=frames,
        events=InMemoryEventSink(),
        push=InMemoryNotificationSink(NotificationChannel.FAKE_PUSH),
        inbox=InMemoryNotificationSink(NotificationChannel.CARDPUTER_INBOX),
        audit=audit,
    )
    asset_inventory = AssetInventoryService(
        ContractValidator(
            load_json(SCHEMAS / "command.schema.json"),
            (load_json(TOOLS / "asset.list.v1.json"),),
        ),
        tools,
        InMemoryAssetRepository(
            (
                AssetRecord(
                    asset_id="asset:edge-01",
                    inventory_id="inventory:primary",
                    organization_id="org:01",
                    display_name="Edge node",
                    asset_type=AssetType.EDGE_NODE,
                    change_state=AssetChangeState.NEW,
                    first_observed_at=NOW - timedelta(days=1),
                    last_observed_at=NOW,
                    private_address="192.0.2.20",
                    credential_reference="vault:edge-node",
                ),
            )
        ),
        audit,
    )
    discovery = PassiveDiscoveryService(
        validator=ContractValidator(
            load_json(SCHEMAS / "command.schema.json"),
            (load_json(TOOLS / "network.passive_discovery.v1.json"),),
        ),
        registry=tools,
        source=InMemoryPassiveDiscoverySource(
            {("org:01", "network:lab", "interface:edge-lan"): ()}
        ),
        audit=audit,
    )
    gateway = DeviceTextCommandGateway(
        DeviceMessageVerifier(protocol_validator, device_registry),
        camera_status=status,
        monitoring=monitoring,
        asset_inventory=asset_inventory,
        discovery=discovery,
    )
    return device, gateway, frames, audit, discovery


def test_menu_to_signed_gateway_lists_stored_assets_without_network() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    device.switch_profile(Profile.INVENTORY, changed_at=NOW, unlocked=True)
    composer = RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(),
        inventories=(InventoryMenuEntry("inventory:primary", "Home lab"),),
    )
    payload = composer.compose(
        "asset.list",
        "inventory:primary",
        requested_at=NOW,
        command_id="command:menu-assets-01",
        correlation_id="correlation:menu-assets-01",
        changes_only=True,
    )
    envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:menu-assets-01",
    )

    outcome = gateway.handle(envelope, execution_context(), received_at=NOW)

    assert isinstance(outcome, AssetInventoryOutcome)
    assert outcome.status is ExecutionStatus.SIMULATED
    assert [asset.asset_id for asset in outcome.assets] == ["asset:edge-01"]
    assert frames.worker_starts == 0
    assert audit.events[0].tool_id == "asset.list"


def test_menu_to_signed_gateway_starts_scoped_passive_discovery() -> None:
    device, gateway, frames, audit, discovery = build_stack()
    device.switch_profile(Profile.INVENTORY, changed_at=NOW, unlocked=True)
    composer = RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(),
        networks=(
            NetworkMenuEntry(
                "network:lab",
                "Lab network",
                "interface:edge-lan",
            ),
        ),
    )
    payload = composer.compose(
        "network.passive_discovery",
        "network:lab",
        requested_at=NOW,
        command_id="command:menu-discovery-01",
        correlation_id="correlation:menu-discovery-01",
        duration_seconds=30,
        maximum_candidates=16,
    )
    envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:menu-discovery-01",
    )
    scoped_context = replace(
        execution_context(),
        operation_scope=OperationScope(
            scope_id="scope:menu-discovery-01",
            organization_id="org:01",
            tool_ids=frozenset({"network.passive_discovery"}),
            target_ids=frozenset({"network:lab"}),
            valid_until=NOW + timedelta(minutes=2),
        ),
    )

    outcome = gateway.handle(envelope, scoped_context, received_at=NOW)

    assert outcome.status is JobState.RUNNING
    assert outcome.job_id == discovery.jobs[0].job_id
    assert frames.worker_starts == 0
    assert audit.events == ()


def test_verified_text_commands_reach_only_the_fixed_fake_services() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    context = execution_context()
    status_command = command()
    status_envelope = device.text_command_message(
        status_command,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )

    status = gateway.handle(
        status_envelope,
        context,
        received_at=NOW,
    )
    device.switch_profile(
        Profile.SENTINEL,
        changed_at=NOW + timedelta(seconds=1),
        unlocked=True,
    )
    monitor_command = command(
        action="camera.monitor",
        profile="sentinel",
        command_id="command:text-monitor-01",
        requested_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:text-monitor-01",
    )
    monitor_envelope = device.text_command_message(
        monitor_command,
        sent_at=NOW + timedelta(seconds=1),
        correlation_id="correlation:text-monitor-01",
    )
    monitoring = gateway.handle(
        monitor_envelope,
        context,
        received_at=NOW + timedelta(seconds=1),
    )

    assert status.status is ExecutionStatus.SIMULATED
    assert monitoring.status is JobState.RUNNING
    assert frames.worker_starts == 1
    assert len(audit.events) == 1


def test_new_signed_envelope_with_identical_command_is_idempotent() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    payload = command()
    first_envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )
    second_envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )

    first = gateway.handle(first_envelope, execution_context(), received_at=NOW)
    second = gateway.handle(second_envelope, execution_context(), received_at=NOW)

    assert second == first
    assert frames.worker_starts == 0
    assert len(audit.events) == 1


@pytest.mark.parametrize(
    ("payload", "sent_at", "envelope_correlation", "reason_code"),
    [
        (
            command(source_device_id="cardputer:other"),
            NOW,
            "correlation:text-status-01",
            "SOURCE_DEVICE_MISMATCH",
        ),
        (
            command(),
            NOW + timedelta(seconds=1),
            "correlation:text-status-01",
            "COMMAND_TIMESTAMP_MISMATCH",
        ),
        (
            command(),
            NOW,
            "correlation:other",
            "CORRELATION_ID_MISMATCH",
        ),
    ],
)
def test_signed_command_metadata_must_match_the_transport(
    payload: dict[str, object],
    sent_at: datetime,
    envelope_correlation: str,
    reason_code: str,
) -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    envelope = device.text_command_message(
        payload,
        sent_at=sent_at,
        correlation_id=envelope_correlation,
    )

    with pytest.raises(DeviceTextCommandRejectedError) as error:
        gateway.handle(envelope, execution_context(), received_at=sent_at)

    assert error.value.reason_code == reason_code
    assert frames.worker_starts == 0
    assert audit.events == ()


def test_unknown_action_is_denied_before_service_or_worker() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    payload = command(action="camera.delete")
    envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )

    with pytest.raises(DeviceTextCommandRejectedError) as error:
        gateway.handle(envelope, execution_context(), received_at=NOW)

    assert error.value.reason_code == "ACTION_NOT_SUPPORTED"
    assert frames.worker_starts == 0
    assert audit.events == ()


def test_authenticated_device_must_match_execution_context() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    envelope = device.text_command_message(
        command(),
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )
    wrong_context = replace(
        execution_context(),
        device=replace(
            execution_context().device,
            device_id="cardputer:other",
        ),
    )

    with pytest.raises(DeviceTextCommandRejectedError) as error:
        gateway.handle(envelope, wrong_context, received_at=NOW)

    assert error.value.reason_code == "DEVICE_CONTEXT_MISMATCH"
    assert frames.worker_starts == 0
    assert audit.events == ()


def test_wrong_verified_payload_type_is_not_dispatched() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    envelope = device.profile_state_message(
        sent_at=NOW,
        correlation_id="correlation:profile-01",
    )

    with pytest.raises(DeviceTextCommandRejectedError) as error:
        gateway.handle(envelope, execution_context(), received_at=NOW)

    assert error.value.reason_code == "TEXT_COMMAND_REQUIRED"
    assert frames.worker_starts == 0
    assert audit.events == ()


def test_spoofed_actor_is_denied_and_audited_by_backend_policy_context() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    envelope = device.text_command_message(
        command(actor_id="user:spoofed"),
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )

    outcome = gateway.handle(envelope, execution_context(), received_at=NOW)

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.reason_code == "COMMAND_CONTEXT_MISMATCH"
    assert frames.worker_starts == 0
    assert audit.events[0].actor_id == "user:01"


def test_changed_command_cannot_reuse_id_through_a_new_envelope() -> None:
    device, gateway, frames, audit, _discovery = build_stack()
    first = command()
    changed = command(target="camera:entrance-01")
    first_envelope = device.text_command_message(
        first,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )
    changed_envelope = device.text_command_message(
        changed,
        sent_at=NOW,
        correlation_id="correlation:text-status-01",
    )
    gateway.handle(first_envelope, execution_context(), received_at=NOW)

    with pytest.raises(CommandRejectedError) as error:
        gateway.handle(changed_envelope, execution_context(), received_at=NOW)

    assert error.value.reason_code == "IDEMPOTENCY_KEY_REUSED"
    assert frames.worker_starts == 0
    assert len(audit.events) == 1

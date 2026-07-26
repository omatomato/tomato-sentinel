import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_orchestrator import (
    AssetChangeState,
    AssetInventoryService,
    AssetRecord,
    AssetType,
    ContractValidator,
    ExecutionContext,
    ExecutionStatus,
    InMemoryAssetRepository,
    InMemoryAuditSink,
    asset_list_manifest,
    asset_outcome_to_contract,
    audit_to_contract,
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
MANIFEST = ROOT / "config" / "tools" / "asset.list.v1.json"
NOW = datetime(2026, 7, 26, 22, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def command(
    *,
    command_id: str = "command:assets-01",
    target: str = "inventory:primary",
    profile: str = "inventory",
    changes_only: bool = True,
) -> dict[str, object]:
    return {
        "contract_version": 1,
        "command_id": command_id,
        "actor_id": "user:01",
        "organization_id": "org:01",
        "source_device_id": "cardputer:01",
        "profile": profile,
        "action": "asset.list",
        "targets": [target],
        "parameters": {"changes_only": changes_only},
        "requested_at": "2026-07-26T22:00:00Z",
        "correlation_id": "correlation:assets-01",
    }


def context() -> ExecutionContext:
    return ExecutionContext(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"inventory_viewer"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"asset_inventory_query"}),
        ),
        resource_grant=ResourceGrant(
            organization_id="org:01",
            resource_ids=frozenset({"inventory:primary"}),
            valid_until=NOW + timedelta(minutes=10),
        ),
    )


def records() -> tuple[AssetRecord, ...]:
    return (
        AssetRecord(
            asset_id="asset:new-camera",
            inventory_id="inventory:primary",
            organization_id="org:01",
            display_name="Garage camera",
            asset_type=AssetType.CAMERA,
            change_state=AssetChangeState.NEW,
            first_observed_at=NOW - timedelta(minutes=2),
            last_observed_at=NOW - timedelta(seconds=10),
            private_address="192.0.2.10",
            credential_reference="vault:garage-camera",
        ),
        AssetRecord(
            asset_id="asset:changed-sensor",
            inventory_id="inventory:primary",
            organization_id="org:01",
            display_name="Door sensor",
            asset_type=AssetType.SENSOR,
            change_state=AssetChangeState.CHANGED,
            first_observed_at=NOW - timedelta(days=10),
            last_observed_at=NOW - timedelta(seconds=20),
            private_address="ble:pseudonymous-private",
            credential_reference=None,
        ),
        AssetRecord(
            asset_id="asset:known-edge",
            inventory_id="inventory:primary",
            organization_id="org:01",
            display_name="Edge node",
            asset_type=AssetType.EDGE_NODE,
            change_state=AssetChangeState.KNOWN,
            first_observed_at=NOW - timedelta(days=30),
            last_observed_at=NOW - timedelta(seconds=30),
            private_address="192.0.2.20",
            credential_reference="vault:edge-node",
        ),
        AssetRecord(
            asset_id="asset:other-tenant",
            inventory_id="inventory:other",
            organization_id="org:other",
            display_name="Other tenant device",
            asset_type=AssetType.NETWORK_DEVICE,
            change_state=AssetChangeState.NEW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            private_address="198.51.100.8",
            credential_reference="vault:other-tenant",
        ),
    )


def build_service() -> tuple[AssetInventoryService, InMemoryAuditSink]:
    registry = ToolRegistry()
    registry.register(asset_list_manifest())
    audit = InMemoryAuditSink()
    return (
        AssetInventoryService(
            ContractValidator(
                load_json(SCHEMAS / "command.schema.json"),
                (load_json(MANIFEST),),
            ),
            registry,
            InMemoryAssetRepository(records()),
            audit,
        ),
        audit,
    )


def test_authorized_inventory_returns_only_sanitized_changes() -> None:
    service, audit = build_service()

    outcome = service.execute(command(), context(), evaluated_at=NOW)
    public = asset_outcome_to_contract(outcome)
    serialized = json.dumps(public)

    assert outcome.status is ExecutionStatus.SIMULATED
    assert [asset.asset_id for asset in outcome.assets] == [
        "asset:changed-sensor",
        "asset:new-camera",
    ]
    assert "192.0.2." not in serialized
    assert "vault:" not in serialized
    assert "other-tenant" not in serialized
    Draft202012Validator(
        load_json(MANIFEST)["result_schema"],
        format_checker=FormatChecker(),
    ).validate(public)
    Draft202012Validator(
        load_json(SCHEMAS / "audit-event.schema.json"),
        format_checker=FormatChecker(),
    ).validate(audit_to_contract(audit.events[0]))


def test_inventory_can_include_known_assets_when_requested() -> None:
    service, _audit = build_service()

    outcome = service.execute(
        command(changes_only=False),
        context(),
        evaluated_at=NOW,
    )

    assert len(outcome.assets) == 3
    assert {asset.change_state for asset in outcome.assets} == {
        AssetChangeState.NEW,
        AssetChangeState.CHANGED,
        AssetChangeState.KNOWN,
    }


def test_registered_empty_inventory_returns_an_empty_result() -> None:
    repository = InMemoryAssetRepository(
        (),
        inventories=(("org:01", "inventory:empty"),),
    )

    resolved = repository.resolve_owned(
        "org:01",
        "inventory:empty",
        changes_only=True,
        maximum_results=128,
    )

    assert resolved == ()


@pytest.mark.parametrize(
    ("payload", "changed_context", "reason_code"),
    [
        (
            command(target="inventory:other"),
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    resource_ids=frozenset({"inventory:other"}),
                ),
            ),
            "TARGET_NOT_ACCESSIBLE",
        ),
        (
            command(),
            replace(
                context(),
                resource_grant=replace(
                    context().resource_grant,
                    resource_ids=frozenset(),
                ),
            ),
            "TARGET_NOT_AUTHORIZED",
        ),
        (command(profile="assistant"), context(), "PROFILE_REQUIRED"),
    ],
)
def test_inventory_denials_return_no_assets(
    payload: dict[str, object],
    changed_context: ExecutionContext,
    reason_code: str,
) -> None:
    service, audit = build_service()

    outcome = service.execute(payload, changed_context, evaluated_at=NOW)

    assert outcome.status is ExecutionStatus.DENIED
    assert outcome.assets == ()
    assert outcome.reason_code == reason_code
    assert audit.events[0].result is ExecutionStatus.DENIED


def test_inventory_command_replay_has_one_audit_side_effect() -> None:
    service, audit = build_service()
    payload = command()

    first = service.execute(payload, context(), evaluated_at=NOW)
    replay = service.execute(
        payload,
        context(),
        evaluated_at=NOW + timedelta(seconds=1),
    )

    assert replay == first
    assert len(audit.events) == 1

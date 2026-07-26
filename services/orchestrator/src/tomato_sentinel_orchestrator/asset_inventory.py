"""Read-only stored asset inventory over a bounded in-memory repository."""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast

from tomato_sentinel_policy import (
    AuthorizationKind,
    Decision,
    PolicyRequest,
    Profile,
    RiskClass,
    ToolManifest,
    ToolRegistry,
    evaluate,
)

from .adapters import AuditSink
from .contracts import CommandRejectedError, ContractValidator
from .execution import (
    audit_event,
    context_matches,
    hash_json,
    plan_hash,
    timestamp_is_fresh,
)
from .models import ExecutionContext, ExecutionStatus, ValidatedCommand

TOOL_ID = "asset.list"
TOOL_VERSION = 1
MAXIMUM_ASSET_RESULTS = 128


class AssetType(StrEnum):
    CAMERA = "camera"
    EDGE_NODE = "edge_node"
    NETWORK_DEVICE = "network_device"
    SENSOR = "sensor"


class AssetChangeState(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    KNOWN = "known"


@dataclass(frozen=True, slots=True)
class AssetRecord:
    asset_id: str
    inventory_id: str
    organization_id: str
    display_name: str
    asset_type: AssetType
    change_state: AssetChangeState
    first_observed_at: datetime
    last_observed_at: datetime
    private_address: str
    credential_reference: str | None


@dataclass(frozen=True, slots=True)
class AssetSummary:
    asset_id: str
    display_name: str
    asset_type: AssetType
    change_state: AssetChangeState
    first_observed_at: datetime
    last_observed_at: datetime


@dataclass(frozen=True, slots=True)
class AssetInventoryOutcome:
    contract_version: int
    command_id: str
    status: ExecutionStatus
    assets: tuple[AssetSummary, ...]
    reason_code: str
    audit_event_id: str


class AssetRepository(Protocol):
    def resolve_owned(
        self,
        organization_id: str,
        inventory_id: str,
        *,
        changes_only: bool,
        maximum_results: int,
    ) -> tuple[AssetSummary, ...] | None: ...


class InMemoryAssetRepository:
    def __init__(
        self,
        assets: Iterable[AssetRecord],
        inventories: Iterable[tuple[str, str]] = (),
    ) -> None:
        bounded = tuple(assets)
        if len(bounded) > 4_096:
            raise ValueError("asset repository exceeds simulation limit")
        identities: set[tuple[str, str]] = set()
        for asset in bounded:
            if (
                not asset.asset_id.startswith("asset:")
                or not asset.inventory_id.startswith("inventory:")
                or not asset.organization_id.startswith("org:")
            ):
                raise ValueError("asset identity is invalid")
            if not asset.display_name or len(asset.display_name) > 120:
                raise ValueError("asset display name is invalid")
            if (
                asset.first_observed_at.tzinfo is None
                or asset.last_observed_at.tzinfo is None
                or asset.last_observed_at < asset.first_observed_at
            ):
                raise ValueError("asset observation timestamps are invalid")
            identity = (asset.organization_id, asset.asset_id)
            if identity in identities:
                raise ValueError("asset identity is duplicated")
            identities.add(identity)
        self._assets = bounded
        self._inventories = {
            (asset.organization_id, asset.inventory_id) for asset in bounded
        }
        for organization_id, inventory_id in inventories:
            if not organization_id.startswith("org:") or not inventory_id.startswith(
                "inventory:"
            ):
                raise ValueError("inventory identity is invalid")
            self._inventories.add((organization_id, inventory_id))

    def resolve_owned(
        self,
        organization_id: str,
        inventory_id: str,
        *,
        changes_only: bool,
        maximum_results: int,
    ) -> tuple[AssetSummary, ...] | None:
        if not 1 <= maximum_results <= MAXIMUM_ASSET_RESULTS:
            raise ValueError("asset result limit is invalid")
        if (organization_id, inventory_id) not in self._inventories:
            return None
        selected = (
            asset
            for asset in self._assets
            if asset.organization_id == organization_id
            and asset.inventory_id == inventory_id
            and (
                not changes_only
                or asset.change_state
                in {AssetChangeState.NEW, AssetChangeState.CHANGED}
            )
        )
        return tuple(
            AssetSummary(
                asset_id=asset.asset_id,
                display_name=asset.display_name,
                asset_type=asset.asset_type,
                change_state=asset.change_state,
                first_observed_at=asset.first_observed_at,
                last_observed_at=asset.last_observed_at,
            )
            for asset in sorted(selected, key=lambda item: item.asset_id)[
                :maximum_results
            ]
        )


def asset_list_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version=TOOL_VERSION,
        risk_class=RiskClass.R0,
        required_profile=Profile.INVENTORY,
        authorization_kind=AuthorizationKind.RESOURCE_GRANT,
        required_roles=frozenset({"inventory_viewer"}),
        required_capabilities=frozenset({"asset_inventory_query"}),
        maximum_targets=1,
    )


class AssetInventoryService:
    def __init__(
        self,
        validator: ContractValidator,
        registry: ToolRegistry,
        assets: AssetRepository,
        audit: AuditSink,
    ) -> None:
        self._validator = validator
        self._registry = registry
        self._assets = assets
        self._audit = audit
        self._outcomes: dict[
            tuple[str, str, str],
            tuple[str, AssetInventoryOutcome],
        ] = {}

    def execute(
        self,
        payload: Mapping[str, object],
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> AssetInventoryOutcome:
        if evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        command = self._validator.validate(payload)
        if command.action != TOOL_ID:
            raise CommandRejectedError("ACTION_NOT_SUPPORTED")
        request_hash = hash_json(payload)
        replay_key = (
            context.actor.organization_id,
            context.actor.actor_id,
            command.command_id,
        )
        replay = self._outcomes.get(replay_key)
        if replay is not None:
            previous_hash, previous_outcome = replay
            if previous_hash != request_hash:
                raise CommandRejectedError("IDEMPOTENCY_KEY_REUSED")
            return previous_outcome

        plan_digest = plan_hash(command)
        if not timestamp_is_fresh(command, evaluated_at):
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "COMMAND_TIMESTAMP_INVALID",
            )
        if not context_matches(command, context):
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "COMMAND_CONTEXT_MISMATCH",
            )

        decision = evaluate(
            PolicyRequest(
                actor=context.actor,
                device=context.device,
                profile=command.profile,
                tool_id=TOOL_ID,
                tool_version=TOOL_VERSION,
                targets=command.targets,
                parameters=command.parameters,
                evaluated_at=evaluated_at,
                plan_hash=plan_digest,
                resource_grant=context.resource_grant,
            ),
            self._registry,
        )
        if decision.decision is not Decision.ALLOW:
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                decision.reason_code.value,
                policy_decision=decision.decision.value,
            )

        changes_only = cast(bool, command.parameters["changes_only"])
        assets = self._assets.resolve_owned(
            context.actor.organization_id,
            command.targets[0],
            changes_only=changes_only,
            maximum_results=MAXIMUM_ASSET_RESULTS,
        )
        if assets is None:
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "TARGET_NOT_ACCESSIBLE",
            )

        event = audit_event(
            command,
            context,
            evaluated_at,
            tool_id=TOOL_ID,
            tool_version=TOOL_VERSION,
            plan_digest=plan_digest,
            policy_decision=decision.decision.value,
            reason_code=decision.reason_code.value,
            result=ExecutionStatus.SIMULATED,
        )
        self._audit.append(event)
        outcome = AssetInventoryOutcome(
            contract_version=1,
            command_id=command.command_id,
            status=ExecutionStatus.SIMULATED,
            assets=assets,
            reason_code=decision.reason_code.value,
            audit_event_id=event.event_id,
        )
        self._outcomes[replay_key] = (request_hash, outcome)
        return outcome

    def _deny_and_remember(
        self,
        replay_key: tuple[str, str, str],
        request_hash: str,
        command: ValidatedCommand,
        context: ExecutionContext,
        evaluated_at: datetime,
        plan_digest: str,
        reason_code: str,
        *,
        policy_decision: str = "deny",
    ) -> AssetInventoryOutcome:
        event = audit_event(
            command,
            context,
            evaluated_at,
            tool_id=TOOL_ID,
            tool_version=TOOL_VERSION,
            plan_digest=plan_digest,
            policy_decision=policy_decision,
            reason_code=reason_code,
            result=ExecutionStatus.DENIED,
        )
        self._audit.append(event)
        outcome = AssetInventoryOutcome(
            contract_version=1,
            command_id=command.command_id,
            status=ExecutionStatus.DENIED,
            assets=(),
            reason_code=reason_code,
            audit_event_id=event.event_id,
        )
        self._outcomes[replay_key] = (request_hash, outcome)
        return outcome


def asset_outcome_to_contract(
    outcome: AssetInventoryOutcome,
) -> dict[str, object]:
    return {
        "contract_version": outcome.contract_version,
        "command_id": outcome.command_id,
        "status": outcome.status.value,
        "assets": [
            {
                **asdict(asset),
                "asset_type": asset.asset_type.value,
                "change_state": asset.change_state.value,
                "first_observed_at": _timestamp(asset.first_observed_at),
                "last_observed_at": _timestamp(asset.last_observed_at),
            }
            for asset in outcome.assets
        ],
        "reason_code": outcome.reason_code,
        "audit_event_id": outcome.audit_event_id,
    }


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")

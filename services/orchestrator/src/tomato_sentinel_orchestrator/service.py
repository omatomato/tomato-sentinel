"""Synchronous R0 command orchestration with deterministic audit."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timedelta

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

from .adapters import AuditSink, CameraRepository
from .contracts import CommandRejectedError, ContractValidator
from .models import (
    AuditEvent,
    CommandOutcome,
    ExecutionContext,
    ExecutionStatus,
    ValidatedCommand,
)

TOOL_ID = "camera.status"
TOOL_VERSION = 1


def camera_status_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version=TOOL_VERSION,
        risk_class=RiskClass.R0,
        required_profile=Profile.ASSISTANT,
        authorization_kind=AuthorizationKind.RESOURCE_GRANT,
        required_roles=frozenset({"viewer"}),
        required_capabilities=frozenset({"camera_status_query"}),
        maximum_targets=32,
    )


class CameraStatusService:
    def __init__(
        self,
        validator: ContractValidator,
        registry: ToolRegistry,
        cameras: CameraRepository,
        audit: AuditSink,
    ) -> None:
        self._validator = validator
        self._registry = registry
        self._cameras = cameras
        self._audit = audit
        self._outcomes: dict[tuple[str, str, str], tuple[str, CommandOutcome]] = {}

    def execute(
        self,
        payload: Mapping[str, object],
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> CommandOutcome:
        if evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        command = self._validator.validate(payload)
        request_hash = _hash_json(payload)
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

        if not _timestamp_is_fresh(command, evaluated_at):
            outcome = self._record_denial(
                command,
                context,
                evaluated_at,
                plan_hash=_plan_hash(command),
                reason_code="COMMAND_TIMESTAMP_INVALID",
            )
            self._outcomes[replay_key] = (request_hash, outcome)
            return outcome

        if not _context_matches(command, context):
            outcome = self._record_denial(
                command,
                context,
                evaluated_at,
                plan_hash=_plan_hash(command),
                reason_code="COMMAND_CONTEXT_MISMATCH",
            )
            self._outcomes[replay_key] = (request_hash, outcome)
            return outcome

        cameras = self._cameras.resolve_owned(
            context.actor.organization_id,
            command.targets,
        )
        if cameras is None:
            outcome = self._record_denial(
                command,
                context,
                evaluated_at,
                plan_hash=_plan_hash(command),
                reason_code="TARGET_NOT_ACCESSIBLE",
            )
            self._outcomes[replay_key] = (request_hash, outcome)
            return outcome

        plan_hash = _plan_hash(command)
        policy_request = PolicyRequest(
            actor=context.actor,
            device=context.device,
            profile=command.profile,
            tool_id=TOOL_ID,
            tool_version=TOOL_VERSION,
            targets=command.targets,
            parameters=command.parameters,
            evaluated_at=evaluated_at,
            plan_hash=plan_hash,
            resource_grant=context.resource_grant,
        )
        decision = evaluate(policy_request, self._registry)
        if decision.decision is not Decision.ALLOW:
            outcome = self._record_denial(
                command,
                context,
                evaluated_at,
                plan_hash=plan_hash,
                reason_code=decision.reason_code.value,
                policy_decision=decision.decision.value,
            )
            self._outcomes[replay_key] = (request_hash, outcome)
            return outcome

        event = _audit_event(
            command,
            context,
            evaluated_at,
            plan_hash=plan_hash,
            policy_decision=decision.decision.value,
            reason_code=decision.reason_code.value,
            result=ExecutionStatus.SIMULATED,
        )
        self._audit.append(event)
        outcome = CommandOutcome(
            contract_version=1,
            command_id=command.command_id,
            status=ExecutionStatus.SIMULATED,
            cameras=cameras,
            reason_code=decision.reason_code.value,
            audit_event_id=event.event_id,
        )
        self._outcomes[replay_key] = (request_hash, outcome)
        return outcome

    def _record_denial(
        self,
        command: ValidatedCommand,
        context: ExecutionContext,
        evaluated_at: datetime,
        *,
        plan_hash: str,
        reason_code: str,
        policy_decision: str = "deny",
    ) -> CommandOutcome:
        event = _audit_event(
            command,
            context,
            evaluated_at,
            plan_hash=plan_hash,
            policy_decision=policy_decision,
            reason_code=reason_code,
            result=ExecutionStatus.DENIED,
        )
        self._audit.append(event)
        return CommandOutcome(
            contract_version=1,
            command_id=command.command_id,
            status=ExecutionStatus.DENIED,
            cameras=(),
            reason_code=reason_code,
            audit_event_id=event.event_id,
        )


def _context_matches(
    command: ValidatedCommand,
    context: ExecutionContext,
) -> bool:
    return (
        command.actor_id == context.actor.actor_id
        and command.organization_id == context.actor.organization_id
        and command.source_device_id == context.device.device_id
        and context.actor.organization_id == context.device.organization_id
    )


def _timestamp_is_fresh(
    command: ValidatedCommand,
    evaluated_at: datetime,
) -> bool:
    return (
        evaluated_at - timedelta(minutes=5)
        <= command.requested_at
        <= evaluated_at + timedelta(seconds=30)
    )


def _plan_hash(command: ValidatedCommand) -> str:
    return _hash_json(
        {
            "action": command.action,
            "parameters": command.parameters,
            "targets": command.targets,
        }
    )


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _audit_event(
    command: ValidatedCommand,
    context: ExecutionContext,
    evaluated_at: datetime,
    *,
    plan_hash: str,
    policy_decision: str,
    reason_code: str,
    result: ExecutionStatus,
) -> AuditEvent:
    event_material = {
        "command_id": command.command_id,
        "actor_id": context.actor.actor_id,
        "organization_id": context.actor.organization_id,
        "result": result.value,
    }
    event_digest = _hash_json(event_material).removeprefix("sha256:")[:32]
    return AuditEvent(
        contract_version=1,
        event_id=f"audit:{event_digest}",
        timestamp=evaluated_at,
        actor_id=context.actor.actor_id,
        organization_id=context.actor.organization_id,
        device_id=context.device.device_id,
        profile=command.profile,
        scope_id=None,
        tool_id=TOOL_ID,
        tool_version=TOOL_VERSION,
        targets=command.targets,
        parameters_hash=_hash_json(command.parameters),
        plan_hash=plan_hash,
        policy_decision=policy_decision,
        reason_code=reason_code,
        confirmation_method=None,
        result=result,
        correlation_id=command.correlation_id,
    )


def outcome_to_contract(outcome: CommandOutcome) -> dict[str, object]:
    cameras = [
        {
            **asdict(camera),
            "status": camera.status.value,
            "observed_at": camera.observed_at.isoformat().replace("+00:00", "Z"),
        }
        for camera in outcome.cameras
    ]
    return {
        "contract_version": outcome.contract_version,
        "command_id": outcome.command_id,
        "status": outcome.status.value,
        "cameras": cameras,
        "reason_code": outcome.reason_code,
        "audit_event_id": outcome.audit_event_id,
    }


def audit_to_contract(event: AuditEvent) -> dict[str, object]:
    return {
        **asdict(event),
        "timestamp": event.timestamp.isoformat().replace("+00:00", "Z"),
        "profile": event.profile.value,
        "result": event.result.value,
        "targets": list(event.targets),
    }

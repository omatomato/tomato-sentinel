"""Shared deterministic execution-boundary helpers."""

import hashlib
import json
from datetime import datetime, timedelta

from .models import (
    AuditEvent,
    ExecutionContext,
    ExecutionStatus,
    ValidatedCommand,
)


def context_matches(
    command: ValidatedCommand,
    context: ExecutionContext,
) -> bool:
    return (
        command.actor_id == context.actor.actor_id
        and command.organization_id == context.actor.organization_id
        and command.source_device_id == context.device.device_id
        and context.actor.organization_id == context.device.organization_id
    )


def timestamp_is_fresh(
    command: ValidatedCommand,
    evaluated_at: datetime,
) -> bool:
    return (
        evaluated_at - timedelta(minutes=5)
        <= command.requested_at
        <= evaluated_at + timedelta(seconds=30)
    )


def hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def plan_hash(command: ValidatedCommand) -> str:
    return hash_json(
        {
            "action": command.action,
            "parameters": command.parameters,
            "targets": command.targets,
        }
    )


def audit_event(
    command: ValidatedCommand,
    context: ExecutionContext,
    evaluated_at: datetime,
    *,
    tool_id: str,
    tool_version: int,
    plan_digest: str,
    policy_decision: str,
    reason_code: str,
    result: ExecutionStatus,
) -> AuditEvent:
    event_material = {
        "command_id": command.command_id,
        "actor_id": context.actor.actor_id,
        "organization_id": context.actor.organization_id,
        "tool_id": tool_id,
        "result": result.value,
    }
    event_digest = hash_json(event_material).removeprefix("sha256:")[:32]
    return AuditEvent(
        contract_version=1,
        event_id=f"audit:{event_digest}",
        timestamp=evaluated_at,
        actor_id=context.actor.actor_id,
        organization_id=context.actor.organization_id,
        device_id=context.device.device_id,
        profile=command.profile,
        scope_id=(
            context.operation_scope.scope_id
            if context.operation_scope is not None
            else None
        ),
        tool_id=tool_id,
        tool_version=tool_version,
        targets=command.targets,
        parameters_hash=hash_json(command.parameters),
        plan_hash=plan_digest,
        policy_decision=policy_decision,
        reason_code=reason_code,
        confirmation_method=None,
        result=result,
        correlation_id=command.correlation_id,
    )

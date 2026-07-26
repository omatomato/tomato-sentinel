"""Cancelable R1 camera-monitoring orchestration over deterministic fakes."""

import hashlib
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import cast

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
from .detection import TemporalPersonConfirmer
from .execution import (
    audit_event,
    context_matches,
    hash_json,
    plan_hash,
    timestamp_is_fresh,
)
from .models import ExecutionContext, ExecutionStatus, ValidatedCommand
from .monitoring_adapters import (
    EventSink,
    FrameSource,
    NotificationSink,
)
from .monitoring_models import (
    JobState,
    JobTransition,
    MonitoringOutcome,
    Notification,
    PersonDetectedEvent,
)
from .state_machine import MonitoringJob

TOOL_ID = "camera.monitor"
TOOL_VERSION = 1
MAXIMUM_FRAMES = 300
MAXIMUM_EVENTS = 1


def camera_monitor_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version=TOOL_VERSION,
        risk_class=RiskClass.R1,
        required_profile=Profile.SENTINEL,
        authorization_kind=AuthorizationKind.RESOURCE_GRANT,
        required_roles=frozenset({"operator"}),
        required_capabilities=frozenset({"camera_monitoring"}),
        maximum_duration_seconds=300,
        maximum_targets=1,
    )


class MonitoringService:
    def __init__(
        self,
        *,
        validator: ContractValidator,
        registry: ToolRegistry,
        cameras: CameraRepository,
        frames: FrameSource,
        events: EventSink,
        push: NotificationSink,
        inbox: NotificationSink,
        audit: AuditSink,
        confirmer: TemporalPersonConfirmer | None = None,
    ) -> None:
        self._validator = validator
        self._registry = registry
        self._cameras = cameras
        self._frames = frames
        self._events = events
        self._push = push
        self._inbox = inbox
        self._audit = audit
        self._confirmer = confirmer or TemporalPersonConfirmer()
        self._jobs: dict[str, MonitoringJob] = {}
        self._commands: dict[
            tuple[str, str, str],
            tuple[str, str | None, MonitoringOutcome],
        ] = {}
        self._job_commands: dict[str, ValidatedCommand] = {}
        self._job_contexts: dict[str, ExecutionContext] = {}
        self._known_events: dict[str, PersonDetectedEvent] = {}

    @property
    def jobs(self) -> tuple[MonitoringJob, ...]:
        return tuple(self._jobs.values())

    def start(
        self,
        payload: Mapping[str, object],
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> MonitoringOutcome:
        _require_aware(evaluated_at)
        command = self._validator.validate(payload)
        if command.action != TOOL_ID:
            raise CommandRejectedError("ACTION_NOT_SUPPORTED")

        request_hash = hash_json(payload)
        replay_key = (
            context.actor.organization_id,
            context.actor.actor_id,
            command.command_id,
        )
        replay = self._commands.get(replay_key)
        if replay is not None:
            previous_hash, job_id, previous_outcome = replay
            if previous_hash != request_hash:
                raise CommandRejectedError("IDEMPOTENCY_KEY_REUSED")
            return self.outcome(job_id) if job_id is not None else previous_outcome

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

        cameras = self._cameras.resolve_owned(
            context.actor.organization_id,
            command.targets,
        )
        if cameras is None:
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "TARGET_NOT_ACCESSIBLE",
            )
        camera = cameras[0]
        if camera.status.value != "online":
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "CAMERA_NOT_AVAILABLE",
            )

        policy_request = PolicyRequest(
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
        )
        decision = evaluate(policy_request, self._registry)
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

        duration_seconds = cast(int, command.parameters["duration_seconds"])
        job_id = _job_id(context, command)
        job = MonitoringJob(
            job_id=job_id,
            organization_id=context.actor.organization_id,
            actor_id=context.actor.actor_id,
            device_id=context.device.device_id,
            camera_id=camera.camera_id,
            camera_display_name=camera.display_name,
            duration_seconds=duration_seconds,
            created_at=evaluated_at,
            plan_hash=plan_digest,
            correlation_id=command.correlation_id,
        )
        job.transition(
            JobState.VALIDATED,
            requested_action="validate",
            actor_id=context.actor.actor_id,
            timestamp=evaluated_at,
            reason="COMMAND_VALIDATED",
        )
        job.transition(
            JobState.AUTHORIZED,
            requested_action="authorize",
            actor_id=context.actor.actor_id,
            timestamp=evaluated_at,
            reason=decision.reason_code.value,
        )
        self._frames.start(job_id, camera.camera_id, MAXIMUM_FRAMES)
        job.transition(
            JobState.RUNNING,
            requested_action="start",
            actor_id=context.actor.actor_id,
            timestamp=evaluated_at,
            reason="SIMULATION_STARTED",
        )
        self._jobs[job_id] = job
        self._job_commands[job_id] = command
        self._job_contexts[job_id] = context
        outcome = self.outcome(job_id)
        self._commands[replay_key] = (request_hash, job_id, outcome)
        return outcome

    def advance(
        self,
        job_id: str,
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> MonitoringOutcome:
        _require_aware(evaluated_at)
        job = self._authorized_job(job_id, context)
        if job.state is not JobState.RUNNING:
            return self.outcome(job_id)
        if evaluated_at >= job.deadline:
            return self._complete(job, evaluated_at, "DURATION_ELAPSED")

        frame = self._frames.next_frame(job_id)
        if frame is None:
            return self._complete(job, evaluated_at, "FRAME_SEQUENCE_EXHAUSTED")
        if frame.observed_at > job.deadline:
            return self._complete(job, evaluated_at, "DURATION_ELAPSED")

        job.record_frame()
        event = self._confirmer.observe(job, frame)
        if (
            event is not None
            and len(job.event_ids) < MAXIMUM_EVENTS
            and job.add_event(event.event_id)
        ):
            self._known_events[event.event_id] = event
            self.publish_event(event, context.actor.actor_id)
        return self.outcome(job_id)

    def run_to_completion(
        self,
        job_id: str,
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> MonitoringOutcome:
        for _ in range(MAXIMUM_FRAMES + 1):
            outcome = self.advance(job_id, context, evaluated_at=evaluated_at)
            if outcome.status is not JobState.RUNNING:
                return outcome
        raise RuntimeError("bounded frame source did not terminate")

    def cancel(
        self,
        job_id: str,
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> MonitoringOutcome:
        _require_aware(evaluated_at)
        job = self._authorized_job(job_id, context)
        if job.state in {
            JobState.COMPLETED,
            JobState.CANCELLED,
            JobState.FAILED,
            JobState.DENIED,
        }:
            return self.outcome(job_id)
        self._frames.cancel(job_id)
        job.transition(
            JobState.CANCELLED,
            requested_action="cancel",
            actor_id=context.actor.actor_id,
            timestamp=evaluated_at,
            reason="CANCELLED_BY_OPERATOR",
        )
        self._append_terminal_audit(
            job,
            evaluated_at,
            reason_code="CANCELLED_BY_OPERATOR",
            result=ExecutionStatus.CANCELLED,
        )
        return self.outcome(job_id)

    def publish_event(
        self,
        event: PersonDetectedEvent,
        recipient_id: str,
    ) -> bool:
        job = self._jobs.get(event.job_id)
        if (
            job is None
            or self._known_events.get(event.event_id) != event
            or event.organization_id != job.organization_id
            or event.camera_id != job.camera_id
            or event.correlation_id != job.correlation_id
            or event.event_type != "person.detected"
            or event.execution_mode != "simulated"
            or recipient_id != job.actor_id
        ):
            raise ValueError("event is not bound to this monitoring job")
        created = self._events.append(event)
        self._push.deliver(event, recipient_id)
        self._inbox.deliver(event, recipient_id)
        return created

    def outcome(self, job_id: str | None) -> MonitoringOutcome:
        if job_id is None:
            raise LookupError("monitoring job not found")
        job = self._jobs[job_id]
        return MonitoringOutcome(
            contract_version=1,
            job_id=job.job_id,
            status=job.state,
            execution_mode="simulated",
            event_ids=job.event_ids,
            reason_code=job.transitions[-1].reason,
        )

    def _authorized_job(
        self,
        job_id: str,
        context: ExecutionContext,
    ) -> MonitoringJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError("monitoring job not found")
        if (
            job.organization_id != context.actor.organization_id
            or job.actor_id != context.actor.actor_id
            or job.device_id != context.device.device_id
        ):
            raise PermissionError("monitoring job is not accessible")
        return job

    def _complete(
        self,
        job: MonitoringJob,
        evaluated_at: datetime,
        reason_code: str,
    ) -> MonitoringOutcome:
        job.transition(
            JobState.COMPLETED,
            requested_action="complete",
            actor_id=job.actor_id,
            timestamp=evaluated_at,
            reason=reason_code,
        )
        self._append_terminal_audit(
            job,
            evaluated_at,
            reason_code="SIMULATION_COMPLETED",
            result=ExecutionStatus.SIMULATED,
        )
        return self.outcome(job.job_id)

    def _append_terminal_audit(
        self,
        job: MonitoringJob,
        evaluated_at: datetime,
        *,
        reason_code: str,
        result: ExecutionStatus,
    ) -> None:
        command = self._job_commands[job.job_id]
        context = self._job_contexts[job.job_id]
        self._audit.append(
            audit_event(
                command,
                context,
                evaluated_at,
                tool_id=TOOL_ID,
                tool_version=TOOL_VERSION,
                plan_digest=job.plan_hash,
                policy_decision="allow",
                reason_code=reason_code,
                result=result,
            )
        )

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
    ) -> MonitoringOutcome:
        self._audit.append(
            audit_event(
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
        )
        outcome = MonitoringOutcome(
            contract_version=1,
            job_id=None,
            status=JobState.DENIED,
            execution_mode="simulated",
            event_ids=(),
            reason_code=reason_code,
        )
        self._commands[replay_key] = (request_hash, None, outcome)
        return outcome


def _job_id(context: ExecutionContext, command: ValidatedCommand) -> str:
    material = (
        f"{context.actor.organization_id}:{context.actor.actor_id}:{command.command_id}"
    ).encode()
    return f"job:{hashlib.sha256(material).hexdigest()[:32]}"


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")


def monitoring_outcome_to_contract(
    outcome: MonitoringOutcome,
) -> dict[str, object]:
    return {
        "contract_version": outcome.contract_version,
        "job_id": outcome.job_id,
        "status": outcome.status.value,
        "execution_mode": outcome.execution_mode,
        "event_ids": list(outcome.event_ids),
        "reason_code": outcome.reason_code,
    }


def transition_to_contract(
    transition: JobTransition,
) -> dict[str, object]:
    return {
        **asdict(transition),
        "previous_state": (
            transition.previous_state.value
            if transition.previous_state is not None
            else None
        ),
        "resulting_state": transition.resulting_state.value,
        "timestamp": transition.timestamp.isoformat().replace("+00:00", "Z"),
    }


def person_event_to_contract(
    event: PersonDetectedEvent,
) -> dict[str, object]:
    return {
        "contract_version": event.contract_version,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "organization_id": event.organization_id,
        "job_id": event.job_id,
        "camera_id": event.camera_id,
        "confidence": event.confidence,
        "frame_count": event.frame_count,
        "first_seen_at": event.first_seen_at.isoformat().replace("+00:00", "Z"),
        "last_seen_at": event.last_seen_at.isoformat().replace("+00:00", "Z"),
        "snapshot_id": event.snapshot_id,
        "detector": {
            "name": event.detector_name,
            "version": event.detector_version,
        },
        "execution_mode": event.execution_mode,
        "correlation_id": event.correlation_id,
    }


def notification_to_contract(
    notification: Notification,
) -> dict[str, object]:
    return {
        **asdict(notification),
        "channel": notification.channel.value,
    }

"""Bounded, cancelable passive-discovery simulation with no network I/O."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
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
from .monitoring_models import JobState, JobTransition
from .state_machine import InvalidTransitionError

TOOL_ID = "network.passive_discovery"
TOOL_VERSION = 1
MAXIMUM_DISCOVERY_DURATION_SECONDS = 120
MAXIMUM_DISCOVERY_CANDIDATES = 128
_TYPED_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
_ALLOWED_PROTOCOLS = frozenset(
    {
        "arp_cache",
        "dhcp_lease",
        "mdns_announcement",
        "ssdp_notification",
        "ws_discovery_announcement",
    }
)
_ALLOWED_PROBABLE_TYPES = frozenset(
    {"camera", "edge_node", "network_device", "sensor", "unknown"}
)

_ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.CREATED: frozenset({JobState.VALIDATED}),
    JobState.VALIDATED: frozenset({JobState.AUTHORIZED}),
    JobState.AUTHORIZED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset(
        {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.DENIED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    candidate_id: str
    organization_id: str
    observer_id: str
    network_id: str
    interface_id: str
    protocols: tuple[str, ...]
    probable_types: tuple[str, ...]
    authentication_required: bool | None
    first_observed_at: datetime
    last_observed_at: datetime
    confidence: float


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    contract_version: int
    job_id: str | None
    status: JobState
    execution_mode: str
    candidates: tuple[DiscoveryCandidate, ...]
    reason_code: str


class PassiveDiscoverySource(Protocol):
    def start(
        self,
        job_id: str,
        organization_id: str,
        network_id: str,
        interface_id: str,
        maximum_candidates: int,
    ) -> bool: ...

    def next_candidate(self, job_id: str) -> DiscoveryCandidate | None: ...

    def cancel(self, job_id: str) -> None: ...


class InMemoryPassiveDiscoverySource:
    """Reviewed candidate fixtures; it never opens a socket."""

    def __init__(
        self,
        sequences: Mapping[
            tuple[str, str, str],
            Iterable[DiscoveryCandidate],
        ],
    ) -> None:
        self._sequences: dict[
            tuple[str, str, str],
            tuple[DiscoveryCandidate, ...],
        ] = {}
        for key, candidates in sequences.items():
            bounded = tuple(candidates)
            if len(bounded) > MAXIMUM_DISCOVERY_CANDIDATES:
                raise ValueError("discovery fixture exceeds candidate limit")
            organization_id, network_id, interface_id = key
            if (
                not _is_typed_id(organization_id, "org:")
                or not _is_typed_id(network_id, "network:")
                or not _is_typed_id(interface_id, "interface:")
            ):
                raise ValueError("discovery fixture scope is invalid")
            seen: set[str] = set()
            for candidate in bounded:
                if not _is_typed_id(
                    candidate.candidate_id, "candidate:"
                ) or not _is_typed_id(candidate.observer_id, "edge:"):
                    raise ValueError("candidate identity is invalid")
                if (
                    candidate.organization_id != organization_id
                    or candidate.network_id != network_id
                    or candidate.interface_id != interface_id
                ):
                    raise ValueError("candidate does not match fixture scope")
                if candidate.candidate_id in seen:
                    raise ValueError("candidate identifier is duplicated")
                if (
                    candidate.first_observed_at.tzinfo is None
                    or candidate.last_observed_at.tzinfo is None
                    or candidate.last_observed_at < candidate.first_observed_at
                ):
                    raise ValueError("candidate timestamps are invalid")
                if isinstance(candidate.confidence, bool) or not (
                    0 <= candidate.confidence <= 1
                ):
                    raise ValueError("candidate confidence is invalid")
                if (
                    not 1 <= len(candidate.protocols) <= 8
                    or len(set(candidate.protocols)) != len(candidate.protocols)
                    or not set(candidate.protocols).issubset(_ALLOWED_PROTOCOLS)
                    or not 1 <= len(candidate.probable_types) <= 8
                    or len(set(candidate.probable_types))
                    != len(candidate.probable_types)
                    or not set(candidate.probable_types).issubset(
                        _ALLOWED_PROBABLE_TYPES
                    )
                ):
                    raise ValueError("candidate classification is invalid")
                if candidate.authentication_required is not None and not isinstance(
                    candidate.authentication_required,
                    bool,
                ):
                    raise ValueError("candidate authentication claim is invalid")
                seen.add(candidate.candidate_id)
            self._sequences[key] = bounded
        self._active: dict[
            str,
            tuple[tuple[DiscoveryCandidate, ...], int],
        ] = {}
        self._cancelled: set[str] = set()
        self.worker_starts = 0

    def start(
        self,
        job_id: str,
        organization_id: str,
        network_id: str,
        interface_id: str,
        maximum_candidates: int,
    ) -> bool:
        if not 1 <= maximum_candidates <= MAXIMUM_DISCOVERY_CANDIDATES:
            raise ValueError("maximum candidate count is invalid")
        if job_id in self._active:
            raise ValueError("discovery worker already exists")
        candidates = self._sequences.get((organization_id, network_id, interface_id))
        if candidates is None:
            return False
        self._active[job_id] = (candidates[:maximum_candidates], 0)
        self.worker_starts += 1
        return True

    def next_candidate(self, job_id: str) -> DiscoveryCandidate | None:
        if job_id in self._cancelled:
            return None
        candidates, index = self._active[job_id]
        if index >= len(candidates):
            return None
        self._active[job_id] = (candidates, index + 1)
        return candidates[index]

    def cancel(self, job_id: str) -> None:
        if job_id in self._active:
            self._cancelled.add(job_id)


class DiscoveryJob:
    def __init__(
        self,
        *,
        job_id: str,
        organization_id: str,
        actor_id: str,
        device_id: str,
        scope_id: str,
        network_id: str,
        interface_id: str,
        duration_seconds: int,
        maximum_candidates: int,
        created_at: datetime,
        plan_hash: str,
        correlation_id: str,
    ) -> None:
        self.job_id = job_id
        self.organization_id = organization_id
        self.actor_id = actor_id
        self.device_id = device_id
        self.scope_id = scope_id
        self.network_id = network_id
        self.interface_id = interface_id
        self.duration_seconds = duration_seconds
        self.maximum_candidates = maximum_candidates
        self.created_at = created_at
        self.deadline = created_at + timedelta(seconds=duration_seconds)
        self.plan_hash = plan_hash
        self.correlation_id = correlation_id
        self.state = JobState.CREATED
        self._candidates: dict[str, DiscoveryCandidate] = {}
        self._transitions: list[JobTransition] = [
            self._make_transition(
                previous_state=None,
                resulting_state=JobState.CREATED,
                requested_action="create",
                actor_id=actor_id,
                timestamp=created_at,
                reason="COMMAND_ACCEPTED",
            )
        ]

    @property
    def candidates(self) -> tuple[DiscoveryCandidate, ...]:
        return tuple(self._candidates.values())

    @property
    def transitions(self) -> tuple[JobTransition, ...]:
        return tuple(self._transitions)

    def add_candidate(self, candidate: DiscoveryCandidate) -> bool:
        if self.state is not JobState.RUNNING:
            raise InvalidTransitionError("candidates require a running job")
        if candidate.candidate_id in self._candidates:
            return False
        if len(self._candidates) >= self.maximum_candidates:
            return False
        self._candidates[candidate.candidate_id] = candidate
        return True

    def transition(
        self,
        resulting_state: JobState,
        *,
        requested_action: str,
        actor_id: str,
        timestamp: datetime,
        reason: str,
    ) -> JobTransition:
        if resulting_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransitionError(
                f"invalid discovery transition: "
                f"{self.state.value} -> {resulting_state.value}"
            )
        if timestamp < self._transitions[-1].timestamp:
            raise InvalidTransitionError("transition timestamp moved backwards")
        previous_state = self.state
        self.state = resulting_state
        transition = self._make_transition(
            previous_state=previous_state,
            resulting_state=resulting_state,
            requested_action=requested_action,
            actor_id=actor_id,
            timestamp=timestamp,
            reason=reason,
        )
        self._transitions.append(transition)
        return transition

    def _make_transition(
        self,
        *,
        previous_state: JobState | None,
        resulting_state: JobState,
        requested_action: str,
        actor_id: str,
        timestamp: datetime,
        reason: str,
    ) -> JobTransition:
        sequence = len(getattr(self, "_transitions", ()))
        material = f"{self.job_id}:{sequence}:{resulting_state.value}".encode()
        digest = hashlib.sha256(material).hexdigest()[:32]
        return JobTransition(
            contract_version=1,
            transition_id=f"transition:{digest}",
            job_id=self.job_id,
            previous_state=previous_state,
            requested_action=requested_action,
            resulting_state=resulting_state,
            actor_id=actor_id,
            timestamp=timestamp,
            reason=reason,
            correlation_id=self.correlation_id,
        )


def passive_discovery_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id=TOOL_ID,
        version=TOOL_VERSION,
        risk_class=RiskClass.R1,
        required_profile=Profile.INVENTORY,
        authorization_kind=AuthorizationKind.OPERATION_SCOPE,
        required_roles=frozenset({"inventory_operator"}),
        required_capabilities=frozenset({"passive_network_observation"}),
        maximum_duration_seconds=MAXIMUM_DISCOVERY_DURATION_SECONDS,
        maximum_targets=1,
    )


class PassiveDiscoveryService:
    def __init__(
        self,
        *,
        validator: ContractValidator,
        registry: ToolRegistry,
        source: PassiveDiscoverySource,
        audit: AuditSink,
    ) -> None:
        self._validator = validator
        self._registry = registry
        self._source = source
        self._audit = audit
        self._jobs: dict[str, DiscoveryJob] = {}
        self._commands: dict[
            tuple[str, str, str],
            tuple[str, str | None, DiscoveryOutcome],
        ] = {}
        self._job_commands: dict[str, ValidatedCommand] = {}
        self._job_contexts: dict[str, ExecutionContext] = {}

    @property
    def jobs(self) -> tuple[DiscoveryJob, ...]:
        return tuple(self._jobs.values())

    def start(
        self,
        payload: Mapping[str, object],
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> DiscoveryOutcome:
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
                operation_scope=context.operation_scope,
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

        duration_seconds = cast(int, command.parameters["duration_seconds"])
        maximum_candidates = cast(int, command.parameters["maximum_candidates"])
        interface_id = cast(str, command.parameters["interface_id"])
        scope = context.operation_scope
        if scope is None:
            raise RuntimeError("allowed discovery requires an operation scope")
        if scope.valid_until < evaluated_at + timedelta(seconds=duration_seconds):
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "SCOPE_EXPIRES_BEFORE_JOB",
            )
        job_id = _job_id(context, command)
        if not self._source.start(
            job_id,
            context.actor.organization_id,
            command.targets[0],
            interface_id,
            maximum_candidates,
        ):
            return self._deny_and_remember(
                replay_key,
                request_hash,
                command,
                context,
                evaluated_at,
                plan_digest,
                "DISCOVERY_SOURCE_NOT_CONFIGURED",
            )

        job = DiscoveryJob(
            job_id=job_id,
            organization_id=context.actor.organization_id,
            actor_id=context.actor.actor_id,
            device_id=context.device.device_id,
            scope_id=scope.scope_id,
            network_id=command.targets[0],
            interface_id=interface_id,
            duration_seconds=duration_seconds,
            maximum_candidates=maximum_candidates,
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
    ) -> DiscoveryOutcome:
        _require_aware(evaluated_at)
        job = self._authorized_job(job_id, context)
        if job.state is not JobState.RUNNING:
            return self.outcome(job_id)
        if evaluated_at >= job.deadline:
            return self._complete(job, evaluated_at, "DURATION_ELAPSED")
        candidate = self._source.next_candidate(job_id)
        if candidate is None:
            return self._complete(job, evaluated_at, "FIXTURE_EXHAUSTED")
        if candidate.organization_id != job.organization_id:
            return self._fail(job, evaluated_at, "CANDIDATE_CONTEXT_MISMATCH")
        job.add_candidate(candidate)
        return self.outcome(job_id)

    def run_to_completion(
        self,
        job_id: str,
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> DiscoveryOutcome:
        job = self._authorized_job(job_id, context)
        for offset in range(job.maximum_candidates + 1):
            outcome = self.advance(
                job_id,
                context,
                evaluated_at=evaluated_at + timedelta(milliseconds=offset),
            )
            if outcome.status is not JobState.RUNNING:
                return outcome
        return self._fail(
            job,
            evaluated_at + timedelta(seconds=1),
            "CANDIDATE_LIMIT_GUARD",
        )

    def cancel(
        self,
        job_id: str,
        context: ExecutionContext,
        *,
        evaluated_at: datetime,
    ) -> DiscoveryOutcome:
        _require_aware(evaluated_at)
        job = self._authorized_job(job_id, context)
        if job.state in {
            JobState.COMPLETED,
            JobState.CANCELLED,
            JobState.FAILED,
        }:
            return self.outcome(job_id)
        self._source.cancel(job_id)
        job.transition(
            JobState.CANCELLED,
            requested_action="cancel",
            actor_id=context.actor.actor_id,
            timestamp=evaluated_at,
            reason="OPERATOR_CANCELLED",
        )
        self._append_terminal_audit(job, ExecutionStatus.CANCELLED, evaluated_at)
        return self.outcome(job_id)

    def outcome(self, job_id: str | None) -> DiscoveryOutcome:
        if job_id is None or job_id not in self._jobs:
            raise KeyError("discovery job is unknown")
        job = self._jobs[job_id]
        reason = (
            job.transitions[-1].reason
            if job.state is not JobState.RUNNING
            else "SIMULATION_RUNNING"
        )
        return DiscoveryOutcome(
            contract_version=1,
            job_id=job.job_id,
            status=job.state,
            execution_mode="simulated",
            candidates=job.candidates,
            reason_code=reason,
        )

    def _complete(
        self,
        job: DiscoveryJob,
        evaluated_at: datetime,
        reason: str,
    ) -> DiscoveryOutcome:
        job.transition(
            JobState.COMPLETED,
            requested_action="complete",
            actor_id=job.actor_id,
            timestamp=evaluated_at,
            reason=reason,
        )
        self._append_terminal_audit(job, ExecutionStatus.SIMULATED, evaluated_at)
        return self.outcome(job.job_id)

    def _fail(
        self,
        job: DiscoveryJob,
        evaluated_at: datetime,
        reason: str,
    ) -> DiscoveryOutcome:
        job.transition(
            JobState.FAILED,
            requested_action="fail",
            actor_id=job.actor_id,
            timestamp=evaluated_at,
            reason=reason,
        )
        self._append_terminal_audit(job, ExecutionStatus.FAILED, evaluated_at)
        return self.outcome(job.job_id)

    def _authorized_job(
        self,
        job_id: str,
        context: ExecutionContext,
    ) -> DiscoveryJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError("discovery job is unknown")
        scope_id = (
            context.operation_scope.scope_id
            if context.operation_scope is not None
            else None
        )
        if (
            job.organization_id != context.actor.organization_id
            or job.actor_id != context.actor.actor_id
            or job.device_id != context.device.device_id
            or job.scope_id != scope_id
        ):
            raise PermissionError("discovery job context mismatch")
        return job

    def _append_terminal_audit(
        self,
        job: DiscoveryJob,
        result: ExecutionStatus,
        evaluated_at: datetime,
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
                reason_code=job.transitions[-1].reason,
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
    ) -> DiscoveryOutcome:
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
        outcome = DiscoveryOutcome(
            contract_version=1,
            job_id=None,
            status=JobState.DENIED,
            execution_mode="simulated",
            candidates=(),
            reason_code=reason_code,
        )
        self._commands[replay_key] = (request_hash, None, outcome)
        return outcome


def discovery_outcome_to_contract(
    outcome: DiscoveryOutcome,
) -> dict[str, object]:
    return {
        "contract_version": outcome.contract_version,
        "job_id": outcome.job_id,
        "status": outcome.status.value,
        "execution_mode": outcome.execution_mode,
        "candidates": [
            discovery_candidate_to_contract(candidate)
            for candidate in outcome.candidates
        ],
        "reason_code": outcome.reason_code,
    }


def discovery_candidate_to_contract(
    candidate: DiscoveryCandidate,
) -> dict[str, object]:
    public = asdict(candidate)
    public.pop("organization_id")
    return {
        "contract_version": 1,
        **public,
        "first_observed_at": _timestamp(candidate.first_observed_at),
        "last_observed_at": _timestamp(candidate.last_observed_at),
        "protocols": list(candidate.protocols),
        "probable_types": list(candidate.probable_types),
        "enrollment_status": "candidate",
        "execution_mode": "simulated",
    }


def _job_id(context: ExecutionContext, command: ValidatedCommand) -> str:
    material = (
        f"{context.actor.organization_id}:{context.actor.actor_id}:{command.command_id}"
    ).encode()
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f"job:discovery-{digest}"


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")


def _is_typed_id(value: str, prefix: str) -> bool:
    return (
        len(value) <= 160
        and value.startswith(prefix)
        and _TYPED_IDENTIFIER.fullmatch(value) is not None
    )

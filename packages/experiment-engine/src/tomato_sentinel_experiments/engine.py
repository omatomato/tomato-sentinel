"""Bounded, auditable experiment execution state machine."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from tomato_sentinel_policy import (
    ActorContext,
    Confirmation,
    Decision,
    DeviceContext,
    OperationScope,
    PolicyRequest,
    ResourceGrant,
    ToolManifest,
    ToolRegistry,
    evaluate,
)

from .capabilities import ValidatedCapabilityReport
from .models import ExecutionLocation, ExperimentPlan, ModuleManifest
from .plans import ExperimentPlanValidator
from .registry import ModuleRegistry


class ExperimentState(StrEnum):
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DENIED = "denied"
    FAILED = "failed"


TERMINAL_STATES = frozenset(
    {
        ExperimentState.COMPLETED,
        ExperimentState.CANCELLED,
        ExperimentState.DENIED,
        ExperimentState.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class ExperimentAuthorizationContext:
    actor: ActorContext
    device: DeviceContext
    operation_scope: OperationScope | None
    resource_grant: ResourceGrant | None = None
    confirmation: Confirmation | None = None
    capability_report: ValidatedCapabilityReport | None = None


@dataclass(frozen=True, slots=True)
class ExperimentStep:
    complete: bool
    progress_percent: int
    metrics: Mapping[str, int | float | str]
    result: Mapping[str, object] | None = None


class ExperimentSession(Protocol):
    def advance(self) -> ExperimentStep: ...

    def cancel(self) -> None: ...


class ExperimentExecutor(Protocol):
    @property
    def executor_id(self) -> str: ...

    def create_session(self, plan: ExperimentPlan) -> ExperimentSession: ...


@dataclass(frozen=True, slots=True)
class ExperimentAuditRecord:
    sequence: int
    timestamp: datetime
    experiment_id: str
    organization_id: str
    actor_id: str
    device_id: str
    executor_edge_id: str | None
    module_id: str
    module_version: int
    plan_hash: str
    scope_id: str
    state: ExperimentState
    reason_code: str
    execution_mode: str


class ExperimentAuditSink(Protocol):
    def append(self, record: ExperimentAuditRecord) -> None: ...


@dataclass(slots=True)
class InMemoryExperimentAuditSink:
    records: list[ExperimentAuditRecord] = field(default_factory=list)

    def append(self, record: ExperimentAuditRecord) -> None:
        self.records.append(record)


@dataclass(slots=True)
class ExperimentJob:
    plan: ExperimentPlan
    state: ExperimentState
    reason_code: str
    progress_percent: int = 0
    metrics: Mapping[str, int | float | str] = field(default_factory=dict)
    result: Mapping[str, object] | None = None
    _session: ExperimentSession | None = field(default=None, repr=False)


class ExperimentEngineRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def build_policy_registry(modules: ModuleRegistry) -> ToolRegistry:
    registry = ToolRegistry()
    for module in modules.modules:
        registry.register(_as_tool_manifest(module))
    return registry


def _as_tool_manifest(module: ModuleManifest) -> ToolManifest:
    return ToolManifest(
        tool_id=module.module_id,
        version=module.version,
        risk_class=module.risk_class,
        required_profile=module.required_profile,
        authorization_kind=module.authorization_kind,
        required_roles=module.required_roles,
        # Execution capability is checked against the identity-bound edge report.
        # It must not be attributed to the Cardputer that submitted the plan.
        required_capabilities=frozenset(),
        requires_confirmation=module.requires_confirmation,
        requires_physical_confirmation=module.requires_physical_confirmation,
        maximum_duration_seconds=module.maximum_duration_seconds,
        maximum_targets=16,
    )


class ExperimentEngine:
    def __init__(
        self,
        *,
        plan_validator: ExperimentPlanValidator,
        module_registry: ModuleRegistry,
        executors: tuple[ExperimentExecutor, ...],
        audit_sink: ExperimentAuditSink,
    ) -> None:
        self._plan_validator = plan_validator
        self._module_registry = module_registry
        self._policy_registry = build_policy_registry(module_registry)
        self._audit_sink = audit_sink
        self._executors = {executor.executor_id: executor for executor in executors}
        if len(self._executors) != len(executors):
            raise ValueError("duplicate executor_id")
        self._jobs: dict[str, ExperimentJob] = {}
        self._audit_sequence = 0

    def start(
        self,
        payload: Mapping[str, object],
        context: ExperimentAuthorizationContext,
        *,
        evaluated_at: datetime,
    ) -> ExperimentJob:
        plan = self._plan_validator.validate(payload)
        existing = self._jobs.get(plan.experiment_id)
        if existing is not None:
            if existing.plan.plan_hash != plan.plan_hash:
                raise ExperimentEngineRejectedError("EXPERIMENT_ID_REUSED")
            return existing

        self._verify_context(plan, context, evaluated_at)
        manifest = self._module_registry.get(plan.module_id, plan.module_version)
        job = ExperimentJob(
            plan=plan,
            state=ExperimentState.VALIDATED,
            reason_code="PLAN_VALIDATED",
        )
        self._jobs[plan.experiment_id] = job
        self._audit(job, context, evaluated_at)

        policy_decision = evaluate(
            PolicyRequest(
                actor=context.actor,
                device=context.device,
                profile=plan.profile,
                tool_id=plan.module_id,
                tool_version=plan.module_version,
                targets=plan.targets,
                parameters=plan.parameters,
                evaluated_at=evaluated_at,
                plan_hash=plan.plan_hash,
                resource_grant=context.resource_grant,
                operation_scope=context.operation_scope,
                confirmation=context.confirmation,
            ),
            self._policy_registry,
        )
        if policy_decision.decision is not Decision.ALLOW:
            job.state = ExperimentState.DENIED
            job.reason_code = policy_decision.reason_code.value
            self._audit(job, context, evaluated_at)
            return job

        job.state = ExperimentState.AUTHORIZED
        job.reason_code = policy_decision.reason_code.value
        self._audit(job, context, evaluated_at)

        executor = self._executors.get(manifest.executor_id)
        if executor is None:
            job.state = ExperimentState.FAILED
            job.reason_code = "EXECUTOR_UNAVAILABLE"
            self._audit(job, context, evaluated_at)
            return job
        job._session = executor.create_session(plan)
        job.state = ExperimentState.RUNNING
        job.reason_code = "EXECUTION_STARTED"
        self._audit(job, context, evaluated_at)
        return job

    def advance(
        self,
        experiment_id: str,
        context: ExperimentAuthorizationContext,
        *,
        advanced_at: datetime,
    ) -> ExperimentJob:
        job = self.get(experiment_id)
        if job.state is not ExperimentState.RUNNING or job._session is None:
            raise ExperimentEngineRejectedError("EXPERIMENT_NOT_RUNNING")
        try:
            step = job._session.advance()
            if not 0 <= step.progress_percent <= 100:
                raise ValueError("progress outside bounds")
            job.progress_percent = step.progress_percent
            job.metrics = dict(step.metrics)
            if step.complete:
                if step.result is None:
                    raise ValueError("completed step without result")
                manifest = self._module_registry.get(
                    job.plan.module_id,
                    job.plan.module_version,
                )
                Draft202012Validator(manifest.result_schema).validate(step.result)
                job.result = dict(step.result)
                job.state = ExperimentState.COMPLETED
                job.reason_code = "SIMULATION_COMPLETED"
                job._session = None
                self._audit(job, context, advanced_at)
        except (ValidationError, ValueError, RuntimeError):
            job.state = ExperimentState.FAILED
            job.reason_code = "EXECUTOR_RESULT_INVALID"
            job._session = None
            self._audit(job, context, advanced_at)
        return job

    def cancel(
        self,
        experiment_id: str,
        context: ExperimentAuthorizationContext,
        *,
        cancelled_at: datetime,
    ) -> ExperimentJob:
        job = self.get(experiment_id)
        if job.state in TERMINAL_STATES:
            return job
        if job._session is not None:
            job._session.cancel()
        job._session = None
        job.state = ExperimentState.CANCELLED
        job.reason_code = "OPERATOR_CANCELLED"
        self._audit(job, context, cancelled_at)
        return job

    def get(self, experiment_id: str) -> ExperimentJob:
        try:
            return self._jobs[experiment_id]
        except KeyError as error:
            raise ExperimentEngineRejectedError("EXPERIMENT_NOT_FOUND") from error

    def _verify_context(
        self,
        plan: ExperimentPlan,
        context: ExperimentAuthorizationContext,
        evaluated_at: datetime,
    ) -> None:
        if (
            context.actor.actor_id != plan.actor_id
            or context.actor.organization_id != plan.organization_id
            or context.device.device_id != plan.source_device_id
            or context.device.organization_id != plan.organization_id
        ):
            raise ExperimentEngineRejectedError("PLAN_CONTEXT_MISMATCH")
        scope = context.operation_scope
        if scope is None or scope.scope_id != plan.operation_scope_id:
            raise ExperimentEngineRejectedError("PLAN_SCOPE_MISMATCH")
        duration = plan.parameters["duration_seconds"]
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise ExperimentEngineRejectedError("PLAN_DURATION_INVALID")
        if scope.valid_until < evaluated_at + timedelta(seconds=duration):
            raise ExperimentEngineRejectedError("SCOPE_TOO_SHORT")
        manifest = self._module_registry.get(plan.module_id, plan.module_version)
        if manifest.execution_location is ExecutionLocation.EDGE:
            report = context.capability_report
            if report is None:
                raise ExperimentEngineRejectedError("EDGE_CAPABILITY_REPORT_REQUIRED")
            if (
                report.organization_id != plan.organization_id
                or report.valid_until < evaluated_at + timedelta(seconds=duration)
            ):
                raise ExperimentEngineRejectedError("EDGE_CAPABILITY_REPORT_INVALID")
            module_key = (plan.module_id, plan.module_version, manifest.executor_id)
            reported = {
                (item.module_id, item.module_version, item.executor_id)
                for item in report.modules
            }
            if module_key not in reported:
                raise ExperimentEngineRejectedError("EDGE_MODULE_UNAVAILABLE")

    def _audit(
        self,
        job: ExperimentJob,
        context: ExperimentAuthorizationContext,
        timestamp: datetime,
    ) -> None:
        self._audit_sequence += 1
        self._audit_sink.append(
            ExperimentAuditRecord(
                sequence=self._audit_sequence,
                timestamp=timestamp,
                experiment_id=job.plan.experiment_id,
                organization_id=job.plan.organization_id,
                actor_id=job.plan.actor_id,
                device_id=job.plan.source_device_id,
                executor_edge_id=(
                    context.capability_report.edge_id
                    if context.capability_report is not None
                    else None
                ),
                module_id=job.plan.module_id,
                module_version=job.plan.module_version,
                plan_hash=job.plan.plan_hash,
                scope_id=job.plan.operation_scope_id,
                state=job.state,
                reason_code=job.reason_code,
                execution_mode=job.plan.execution_mode,
            )
        )

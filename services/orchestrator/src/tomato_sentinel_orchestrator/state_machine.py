"""Explicit, bounded state machine for long-running monitoring jobs."""

import hashlib
from datetime import datetime, timedelta

from .monitoring_models import JobState, JobTransition

_ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.CREATED: frozenset({JobState.VALIDATED, JobState.DENIED}),
    JobState.VALIDATED: frozenset({JobState.AUTHORIZED, JobState.DENIED}),
    JobState.AUTHORIZED: frozenset(
        {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.RUNNING: frozenset(
        {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.DENIED: frozenset(),
}


class InvalidTransitionError(ValueError):
    pass


class MonitoringJob:
    def __init__(
        self,
        *,
        job_id: str,
        organization_id: str,
        actor_id: str,
        device_id: str,
        camera_id: str,
        camera_display_name: str,
        duration_seconds: int,
        created_at: datetime,
        plan_hash: str,
        correlation_id: str,
    ) -> None:
        self.job_id = job_id
        self.organization_id = organization_id
        self.actor_id = actor_id
        self.device_id = device_id
        self.camera_id = camera_id
        self.camera_display_name = camera_display_name
        self.duration_seconds = duration_seconds
        self.created_at = created_at
        self.deadline = created_at + timedelta(seconds=duration_seconds)
        self.plan_hash = plan_hash
        self.correlation_id = correlation_id
        self.state = JobState.CREATED
        self.frames_processed = 0
        self._event_ids: list[str] = []
        self._transitions: list[JobTransition] = []
        self._transitions.append(
            self._make_transition(
                previous_state=None,
                resulting_state=JobState.CREATED,
                requested_action="create",
                actor_id=actor_id,
                timestamp=created_at,
                reason="COMMAND_ACCEPTED",
            )
        )

    @property
    def transitions(self) -> tuple[JobTransition, ...]:
        return tuple(self._transitions)

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(self._event_ids)

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
                f"invalid transition: {self.state.value} -> {resulting_state.value}"
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

    def record_frame(self) -> None:
        if self.state is not JobState.RUNNING:
            raise InvalidTransitionError("frames require a running job")
        self.frames_processed += 1
        if self.frames_processed > 300:
            raise InvalidTransitionError("frame limit exceeded")

    def add_event(self, event_id: str) -> bool:
        if event_id in self._event_ids:
            return False
        if len(self._event_ids) >= 1:
            return False
        self._event_ids.append(event_id)
        return True

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
        sequence = len(self._transitions)
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

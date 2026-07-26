"""Domain values for bounded simulated camera monitoring."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobState(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DENIED = "denied"


class NotificationChannel(StrEnum):
    FAKE_PUSH = "fake_push"
    CARDPUTER_INBOX = "cardputer_inbox"


@dataclass(frozen=True, slots=True)
class FrameObservation:
    frame_id: str
    observed_at: datetime
    person_confidence: float | None


@dataclass(frozen=True, slots=True)
class JobTransition:
    contract_version: int
    transition_id: str
    job_id: str
    previous_state: JobState | None
    requested_action: str
    resulting_state: JobState
    actor_id: str
    timestamp: datetime
    reason: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class PersonDetectedEvent:
    contract_version: int
    event_id: str
    event_type: str
    organization_id: str
    job_id: str
    camera_id: str
    confidence: float
    frame_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    snapshot_id: None
    detector_name: str
    detector_version: str
    execution_mode: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class Notification:
    contract_version: int
    notification_id: str
    event_id: str
    recipient_id: str
    channel: NotificationChannel
    title: str
    body: str
    idempotency_key: str
    delivery_status: str


@dataclass(frozen=True, slots=True)
class MonitoringOutcome:
    contract_version: int
    job_id: str | None
    status: JobState
    execution_mode: str
    event_ids: tuple[str, ...]
    reason_code: str

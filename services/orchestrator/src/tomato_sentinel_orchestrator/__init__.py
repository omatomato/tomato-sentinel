"""Public API for the simulated orchestrator slice."""

from .adapters import (
    AuditSink,
    CameraRepository,
    InMemoryAuditSink,
    InMemoryCameraRepository,
)
from .contracts import CommandRejectedError, ContractValidator
from .detection import TemporalPersonConfirmer
from .models import (
    AuditEvent,
    CameraRecord,
    CameraState,
    CameraStatus,
    CommandOutcome,
    ExecutionContext,
    ExecutionStatus,
)
from .monitoring_adapters import (
    EventSink,
    FrameSource,
    InMemoryEventSink,
    InMemoryFrameSource,
    InMemoryNotificationSink,
    NotificationSink,
)
from .monitoring_models import (
    FrameObservation,
    JobState,
    JobTransition,
    MonitoringOutcome,
    Notification,
    NotificationChannel,
    PersonDetectedEvent,
)
from .monitoring_service import (
    MonitoringService,
    camera_monitor_manifest,
    monitoring_outcome_to_contract,
    notification_to_contract,
    person_event_to_contract,
    transition_to_contract,
)
from .service import (
    CameraStatusService,
    audit_to_contract,
    camera_status_manifest,
    outcome_to_contract,
)
from .state_machine import InvalidTransitionError, MonitoringJob

__all__ = [
    "AuditEvent",
    "AuditSink",
    "CameraRecord",
    "CameraRepository",
    "CameraState",
    "CameraStatus",
    "CameraStatusService",
    "CommandOutcome",
    "CommandRejectedError",
    "ContractValidator",
    "EventSink",
    "ExecutionContext",
    "ExecutionStatus",
    "FrameObservation",
    "FrameSource",
    "InMemoryAuditSink",
    "InMemoryCameraRepository",
    "InMemoryEventSink",
    "InMemoryFrameSource",
    "InMemoryNotificationSink",
    "InvalidTransitionError",
    "JobState",
    "JobTransition",
    "MonitoringJob",
    "MonitoringOutcome",
    "MonitoringService",
    "Notification",
    "NotificationChannel",
    "NotificationSink",
    "PersonDetectedEvent",
    "TemporalPersonConfirmer",
    "audit_to_contract",
    "camera_monitor_manifest",
    "camera_status_manifest",
    "monitoring_outcome_to_contract",
    "notification_to_contract",
    "outcome_to_contract",
    "person_event_to_contract",
    "transition_to_contract",
]

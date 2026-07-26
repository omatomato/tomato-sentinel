"""Public API for the simulated orchestrator slice."""

from .adapters import (
    AuditSink,
    CameraRepository,
    InMemoryAuditSink,
    InMemoryCameraRepository,
)
from .contracts import CommandRejectedError, ContractValidator
from .models import (
    AuditEvent,
    CameraRecord,
    CameraState,
    CameraStatus,
    CommandOutcome,
    ExecutionContext,
    ExecutionStatus,
)
from .service import (
    CameraStatusService,
    audit_to_contract,
    camera_status_manifest,
    outcome_to_contract,
)

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
    "ExecutionContext",
    "ExecutionStatus",
    "InMemoryAuditSink",
    "InMemoryCameraRepository",
    "audit_to_contract",
    "camera_status_manifest",
    "outcome_to_contract",
]

"""Protocols and deterministic in-memory adapters for the simulated slice."""

from collections.abc import Iterable
from typing import Protocol

from .models import AuditEvent, CameraRecord, CameraStatus


class CameraRepository(Protocol):
    def resolve_owned(
        self,
        organization_id: str,
        camera_ids: tuple[str, ...],
    ) -> tuple[CameraStatus, ...] | None:
        """Return sanitized owned state, or None without leaking existence."""


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> bool:
        """Append once, returning False only for an identical replay."""


class InMemoryCameraRepository:
    def __init__(self, cameras: Iterable[CameraRecord]) -> None:
        self._cameras = {camera.camera_id: camera for camera in cameras}

    def resolve_owned(
        self,
        organization_id: str,
        camera_ids: tuple[str, ...],
    ) -> tuple[CameraStatus, ...] | None:
        resolved: list[CameraStatus] = []
        for camera_id in camera_ids:
            camera = self._cameras.get(camera_id)
            if camera is None or camera.organization_id != organization_id:
                return None
            resolved.append(
                CameraStatus(
                    camera_id=camera.camera_id,
                    display_name=camera.display_name,
                    status=camera.status,
                    observed_at=camera.observed_at,
                )
            )
        return tuple(resolved)


class InMemoryAuditSink:
    def __init__(self) -> None:
        self._events: dict[str, AuditEvent] = {}

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events.values())

    def append(self, event: AuditEvent) -> bool:
        existing = self._events.get(event.event_id)
        if existing is None:
            self._events[event.event_id] = event
            return True
        if existing != event:
            raise ValueError("audit event identifier collision")
        return False

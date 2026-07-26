"""Bounded fake adapters for frames, events, notifications and inbox entries."""

import hashlib
from collections.abc import Iterable
from itertools import islice, pairwise
from typing import Protocol

from .monitoring_models import (
    FrameObservation,
    Notification,
    NotificationChannel,
    PersonDetectedEvent,
)


class FrameSource(Protocol):
    def start(self, job_id: str, camera_id: str, maximum_frames: int) -> None: ...

    def next_frame(self, job_id: str) -> FrameObservation | None: ...

    def cancel(self, job_id: str) -> None: ...


class EventSink(Protocol):
    def append(self, event: PersonDetectedEvent) -> bool: ...


class NotificationSink(Protocol):
    def deliver(
        self,
        event: PersonDetectedEvent,
        recipient_id: str,
    ) -> bool: ...


class InMemoryFrameSource:
    def __init__(
        self,
        sequences: dict[str, Iterable[FrameObservation]],
    ) -> None:
        self._sequences: dict[str, tuple[FrameObservation, ...]] = {}
        for camera_id, frames in sequences.items():
            bounded = tuple(islice(frames, 301))
            if len(bounded) > 300:
                raise ValueError("fake frame sequence exceeds 300 frames")
            if any(frame.observed_at.tzinfo is None for frame in bounded):
                raise ValueError("frame timestamps must be timezone-aware")
            if any(
                frame.person_confidence is not None
                and (
                    isinstance(frame.person_confidence, bool)
                    or not 0 <= frame.person_confidence <= 1
                )
                for frame in bounded
            ):
                raise ValueError("frame confidence must be within [0, 1]")
            if any(
                current.observed_at < previous.observed_at
                for previous, current in pairwise(bounded)
            ):
                raise ValueError("frame timestamps must be monotonic")
            self._sequences[camera_id] = bounded
        self._active: dict[str, tuple[tuple[FrameObservation, ...], int]] = {}
        self._cancelled: set[str] = set()
        self.worker_starts = 0

    def start(self, job_id: str, camera_id: str, maximum_frames: int) -> None:
        if not 1 <= maximum_frames <= 300:
            raise ValueError("maximum_frames must be within [1, 300]")
        if job_id in self._active:
            raise ValueError("frame worker already exists")
        frames = self._sequences.get(camera_id, ())[:maximum_frames]
        self._active[job_id] = (frames, 0)
        self.worker_starts += 1

    def next_frame(self, job_id: str) -> FrameObservation | None:
        if job_id in self._cancelled:
            return None
        frames, index = self._active[job_id]
        if index >= len(frames):
            return None
        self._active[job_id] = (frames, index + 1)
        return frames[index]

    def cancel(self, job_id: str) -> None:
        if job_id in self._active:
            self._cancelled.add(job_id)


class InMemoryEventSink:
    def __init__(self) -> None:
        self._events: dict[str, PersonDetectedEvent] = {}

    @property
    def events(self) -> tuple[PersonDetectedEvent, ...]:
        return tuple(self._events.values())

    def append(self, event: PersonDetectedEvent) -> bool:
        existing = self._events.get(event.event_id)
        if existing is None:
            self._events[event.event_id] = event
            return True
        if existing != event:
            raise ValueError("event identifier collision")
        return False


class InMemoryNotificationSink:
    def __init__(self, channel: NotificationChannel) -> None:
        self.channel = channel
        self._deliveries: dict[str, Notification] = {}

    @property
    def deliveries(self) -> tuple[Notification, ...]:
        return tuple(self._deliveries.values())

    def deliver(
        self,
        event: PersonDetectedEvent,
        recipient_id: str,
    ) -> bool:
        material = f"{event.event_id}:{recipient_id}:{self.channel.value}".encode()
        digest = hashlib.sha256(material).hexdigest()
        idempotency_key = f"idem:{digest}"
        notification = Notification(
            contract_version=1,
            notification_id=f"notification:{digest[:32]}",
            event_id=event.event_id,
            recipient_id=recipient_id,
            channel=self.channel,
            title="Person detected",
            body="A person was detected by an authorized camera.",
            idempotency_key=idempotency_key,
            delivery_status="simulated",
        )
        existing = self._deliveries.get(idempotency_key)
        if existing is None:
            self._deliveries[idempotency_key] = notification
            return True
        if existing != notification:
            raise ValueError("notification idempotency collision")
        return False

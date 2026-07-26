"""Deterministic temporal confirmation over metadata-only fake frames."""

import hashlib

from .monitoring_models import FrameObservation, PersonDetectedEvent
from .state_machine import MonitoringJob


class TemporalPersonConfirmer:
    def __init__(
        self,
        *,
        confidence_threshold: float = 0.8,
        minimum_frames: int = 3,
    ) -> None:
        if not 0 < confidence_threshold <= 1:
            raise ValueError("confidence threshold must be within (0, 1]")
        if minimum_frames < 2:
            raise ValueError("temporal confirmation requires at least two frames")
        if minimum_frames > 300:
            raise ValueError("temporal confirmation cannot exceed frame limit")
        self._confidence_threshold = confidence_threshold
        self._minimum_frames = minimum_frames
        self._runs: dict[str, list[FrameObservation]] = {}
        self._emitted_jobs: set[str] = set()

    def observe(
        self,
        job: MonitoringJob,
        frame: FrameObservation,
    ) -> PersonDetectedEvent | None:
        if job.job_id in self._emitted_jobs:
            return None
        confidence = frame.person_confidence
        if confidence is None or confidence < self._confidence_threshold:
            self._runs[job.job_id] = []
            return None

        run = self._runs.setdefault(job.job_id, [])
        run.append(frame)
        if len(run) < self._minimum_frames:
            return None

        confirmed = tuple(run[-self._minimum_frames :])
        material = (
            f"{job.job_id}:{confirmed[0].frame_id}:{confirmed[-1].frame_id}".encode()
        )
        digest = hashlib.sha256(material).hexdigest()[:32]
        self._emitted_jobs.add(job.job_id)
        return PersonDetectedEvent(
            contract_version=1,
            event_id=f"event:{digest}",
            event_type="person.detected",
            organization_id=job.organization_id,
            job_id=job.job_id,
            camera_id=job.camera_id,
            confidence=min(
                frame.person_confidence
                for frame in confirmed
                if frame.person_confidence is not None
            ),
            frame_count=len(confirmed),
            first_seen_at=confirmed[0].observed_at,
            last_seen_at=confirmed[-1].observed_at,
            snapshot_id=None,
            detector_name="fake-person-detector",
            detector_version="1.0.0",
            execution_mode="simulated",
            correlation_id=job.correlation_id,
        )

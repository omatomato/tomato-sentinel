"""Bounded push-to-talk capture for the host-side Cardputer simulator."""

import base64
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import BoardProfile

MAXIMUM_CAPTURE_DURATION_MS = 15_000
MAXIMUM_ENCODED_AUDIO_BYTES = 18_000


class AudioCaptureState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    READY = "ready"
    CANCELLED = "cancelled"


class AudioCaptureLimitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AudioCaptureMetadata:
    capture_id: str
    recorded_at: datetime
    completed_at: datetime
    duration_ms: int
    byte_length: int


class PushToTalkRecorder:
    """Keeps one simulated encoded capture in a bounded mutable buffer."""

    def __init__(self, board_profile: BoardProfile) -> None:
        if "microphone" not in board_profile.capabilities:
            raise ValueError("board profile has no trusted microphone capability")
        self._buffer = bytearray()
        self._state = AudioCaptureState.IDLE
        self._indicator = "MIC: IDLE"
        self._capture_id: str | None = None
        self._recorded_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._duration_ms = 0

    @property
    def state(self) -> AudioCaptureState:
        return self._state

    @property
    def indicator(self) -> str:
        return self._indicator

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def press(self, capture_id: str, *, recorded_at: datetime) -> None:
        _require_aware(recorded_at)
        if self._state not in {
            AudioCaptureState.IDLE,
            AudioCaptureState.CANCELLED,
        }:
            raise RuntimeError("push-to-talk recorder is not ready")
        if re.fullmatch(r"capture:[A-Za-z0-9][A-Za-z0-9._-]*", capture_id) is None:
            raise ValueError("capture ID must be typed")
        self._clear_buffer()
        self._capture_id = capture_id
        self._recorded_at = recorded_at
        self._completed_at = None
        self._duration_ms = 0
        self._state = AudioCaptureState.RECORDING
        self._indicator = "MIC: RECORDING"

    def append_encoded(self, chunk: bytes, *, duration_ms: int) -> None:
        if self._state is not AudioCaptureState.RECORDING:
            raise RuntimeError("audio capture is not recording")
        if not chunk or duration_ms <= 0:
            raise ValueError("audio chunk and duration must be positive")
        if (
            len(self._buffer) + len(chunk) > MAXIMUM_ENCODED_AUDIO_BYTES
            or self._duration_ms + duration_ms > MAXIMUM_CAPTURE_DURATION_MS
        ):
            self._cancel_with_indicator("MIC: LIMIT REACHED")
            raise AudioCaptureLimitError("push-to-talk capture limit reached")
        self._buffer.extend(chunk)
        self._duration_ms += duration_ms

    def release(self, *, completed_at: datetime) -> AudioCaptureMetadata:
        _require_aware(completed_at)
        if self._state is not AudioCaptureState.RECORDING:
            raise RuntimeError("audio capture is not recording")
        if not self._buffer or self._duration_ms == 0:
            self._cancel_with_indicator("MIC: CANCELLED")
            raise ValueError("empty audio capture")
        if self._recorded_at is None or completed_at < self._recorded_at:
            self._cancel_with_indicator("MIC: CANCELLED")
            raise ValueError("audio capture timestamps are invalid")
        self._completed_at = completed_at
        self._state = AudioCaptureState.READY
        self._indicator = "MIC: READY"
        return self.metadata()

    def cancel(self) -> None:
        if self._state not in {
            AudioCaptureState.RECORDING,
            AudioCaptureState.READY,
        }:
            raise RuntimeError("there is no active audio capture")
        self._cancel_with_indicator("MIC: CANCELLED")

    def payload(self) -> dict[str, object]:
        metadata = self.metadata()
        if self._state is not AudioCaptureState.READY:
            raise RuntimeError("audio capture is not ready for upload")
        return {
            "contract_version": 1,
            "capture_id": metadata.capture_id,
            "recorded_at": _timestamp(metadata.recorded_at),
            "completed_at": _timestamp(metadata.completed_at),
            "audio": {
                "encoding": "opus",
                "sample_rate": 16_000,
                "channels": 1,
                "duration_ms": metadata.duration_ms,
                "byte_length": metadata.byte_length,
                "content_base64": base64.b64encode(self._buffer).decode("ascii"),
            },
            "retention": "delete_after_processing",
        }

    def acknowledge_processed(
        self,
        capture_id: str,
        *,
        succeeded: bool,
    ) -> None:
        if self._state is not AudioCaptureState.READY:
            raise RuntimeError("audio capture is not awaiting acknowledgement")
        if capture_id != self._capture_id:
            raise ValueError("capture acknowledgement does not match")
        if not succeeded:
            return
        self._clear()

    def metadata(self) -> AudioCaptureMetadata:
        if (
            self._capture_id is None
            or self._recorded_at is None
            or self._completed_at is None
        ):
            raise RuntimeError("audio capture metadata is incomplete")
        return AudioCaptureMetadata(
            capture_id=self._capture_id,
            recorded_at=self._recorded_at,
            completed_at=self._completed_at,
            duration_ms=self._duration_ms,
            byte_length=len(self._buffer),
        )

    def _cancel_with_indicator(self, indicator: str) -> None:
        self._clear_buffer()
        self._capture_id = None
        self._recorded_at = None
        self._completed_at = None
        self._duration_ms = 0
        self._state = AudioCaptureState.CANCELLED
        self._indicator = indicator

    def _clear(self) -> None:
        self._clear_buffer()
        self._capture_id = None
        self._recorded_at = None
        self._completed_at = None
        self._duration_ms = 0
        self._state = AudioCaptureState.IDLE
        self._indicator = "MIC: IDLE"

    def _clear_buffer(self) -> None:
        self._buffer[:] = b"\x00" * len(self._buffer)
        self._buffer.clear()


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

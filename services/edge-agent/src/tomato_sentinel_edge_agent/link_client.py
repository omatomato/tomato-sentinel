"""Bounded lifecycle for the edge agent's future outbound Tomato Link."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

MAXIMUM_CONNECT_ATTEMPTS = 5
HEARTBEAT_TIMEOUT = timedelta(seconds=30)
_BACKOFF_SECONDS = (1, 2, 4, 8, 16)


class OutboundLinkRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class OutboundLinkState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BACKOFF = "backoff"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class OutboundLinkStatus:
    state: OutboundLinkState
    attempt: int
    retry_at: datetime | None
    last_heartbeat_at: datetime | None


class OutboundTomatoLinkClient:
    """Transport-independent fail-closed connection state machine."""

    def __init__(self) -> None:
        self._state = OutboundLinkState.DISCONNECTED
        self._attempt = 0
        self._retry_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None

    @property
    def status(self) -> OutboundLinkStatus:
        return OutboundLinkStatus(
            state=self._state,
            attempt=self._attempt,
            retry_at=self._retry_at,
            last_heartbeat_at=self._last_heartbeat_at,
        )

    def start(self, *, now: datetime) -> None:
        _require_aware(now)
        if self._state is not OutboundLinkState.DISCONNECTED:
            raise OutboundLinkRejectedError("LINK_CLIENT_START_DENIED")
        self._state = OutboundLinkState.CONNECTING

    def connected(self, *, now: datetime) -> None:
        _require_aware(now)
        if self._state is not OutboundLinkState.CONNECTING:
            raise OutboundLinkRejectedError("LINK_CLIENT_CONNECT_STATE_INVALID")
        self._state = OutboundLinkState.CONNECTED
        self._attempt = 0
        self._retry_at = None
        self._last_heartbeat_at = now

    def heartbeat(self, *, now: datetime) -> None:
        _require_aware(now)
        if self._state is not OutboundLinkState.CONNECTED:
            raise OutboundLinkRejectedError("LINK_CLIENT_NOT_CONNECTED")
        if self._last_heartbeat_at is not None and now < self._last_heartbeat_at:
            raise OutboundLinkRejectedError("LINK_CLIENT_TIME_REVERSED")
        self._last_heartbeat_at = now

    def connection_failed(self, *, now: datetime) -> None:
        _require_aware(now)
        if self._state not in {
            OutboundLinkState.CONNECTING,
            OutboundLinkState.CONNECTED,
        }:
            raise OutboundLinkRejectedError("LINK_CLIENT_FAILURE_STATE_INVALID")
        self._attempt += 1
        self._last_heartbeat_at = None
        if self._attempt >= MAXIMUM_CONNECT_ATTEMPTS:
            self._state = OutboundLinkState.STOPPED
            self._retry_at = None
            return
        self._state = OutboundLinkState.BACKOFF
        self._retry_at = now + timedelta(seconds=_BACKOFF_SECONDS[self._attempt - 1])

    def tick(self, *, now: datetime) -> None:
        _require_aware(now)
        if self._state is OutboundLinkState.CONNECTED:
            if (
                self._last_heartbeat_at is not None
                and now - self._last_heartbeat_at > HEARTBEAT_TIMEOUT
            ):
                self.connection_failed(now=now)
            return
        if (
            self._state is OutboundLinkState.BACKOFF
            and self._retry_at is not None
            and now >= self._retry_at
        ):
            self._state = OutboundLinkState.CONNECTING
            self._retry_at = None

    def stop(self, *, now: datetime) -> None:
        _require_aware(now)
        self._state = OutboundLinkState.STOPPED
        self._retry_at = None
        self._last_heartbeat_at = None


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise OutboundLinkRejectedError("LINK_CLIENT_TIMEZONE_REQUIRED")

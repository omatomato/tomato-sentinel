"""Sanitized operator-visible state for a governed Tomato Link session."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .link_client import OutboundLinkState, OutboundLinkStatus


class LinkPresentationRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class OperatorLinkState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    SECURE = "secure"
    DEGRADED = "degraded"
    REVOKED = "revoked"
    STOPPED = "stopped"


_INDICATORS = {
    OperatorLinkState.DISCONNECTED: "LINK: OFFLINE",
    OperatorLinkState.CONNECTING: "LINK: CONNECTING",
    OperatorLinkState.SECURE: "LINK: SECURE",
    OperatorLinkState.DEGRADED: "LINK: DEGRADED",
    OperatorLinkState.REVOKED: "LINK: REVOKED",
    OperatorLinkState.STOPPED: "LINK: STOPPED",
}


@dataclass(frozen=True, slots=True)
class OperatorLinkView:
    state: OperatorLinkState
    relay_reachable: bool
    end_to_end_encrypted: bool
    cancellation_lane_ready: bool
    session_expires_at: datetime | None
    credential_revision: int | None
    observed_at: datetime

    def to_contract(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "state": self.state.value,
            "indicator": _INDICATORS[self.state],
            "relay_reachable": self.relay_reachable,
            "end_to_end_encrypted": self.end_to_end_encrypted,
            "cancellation_lane_ready": self.cancellation_lane_ready,
            "session_expires_at": (
                _timestamp(self.session_expires_at)
                if self.session_expires_at is not None
                else None
            ),
            "credential_revision": self.credential_revision,
            "observed_at": _timestamp(self.observed_at),
            "execution_mode": "simulation",
        }


def present_link_status(
    transport: OutboundLinkStatus,
    *,
    now: datetime,
    session_expires_at: datetime | None,
    credential_revision: int | None,
    credential_revoked: bool,
    cancellation_lane_ready: bool,
) -> OperatorLinkView:
    _require_aware(now)
    if session_expires_at is not None:
        _require_aware(session_expires_at)
    relay_reachable = transport.state is OutboundLinkState.CONNECTED
    session_current = (
        session_expires_at is not None
        and credential_revision is not None
        and now < session_expires_at
    )
    control_ready = (
        relay_reachable
        and session_current
        and cancellation_lane_ready
        and not credential_revoked
    )
    secure = control_ready

    if credential_revoked:
        state = OperatorLinkState.REVOKED
    elif secure:
        state = OperatorLinkState.SECURE
    elif relay_reachable:
        state = OperatorLinkState.DEGRADED
    elif transport.state is OutboundLinkState.CONNECTING:
        state = OperatorLinkState.CONNECTING
    elif transport.state is OutboundLinkState.STOPPED:
        state = OperatorLinkState.STOPPED
    else:
        state = OperatorLinkState.DISCONNECTED
    return OperatorLinkView(
        state=state,
        relay_reachable=relay_reachable,
        end_to_end_encrypted=secure,
        cancellation_lane_ready=control_ready,
        session_expires_at=session_expires_at,
        credential_revision=credential_revision,
        observed_at=now,
    )


def _timestamp(value: datetime) -> str:
    _require_aware(value)
    return value.isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise LinkPresentationRejectedError("LINK_STATUS_TIMEZONE_REQUIRED")

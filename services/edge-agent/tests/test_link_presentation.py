import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_edge_agent.link_client import (
    OutboundLinkState,
    OutboundLinkStatus,
)
from tomato_sentinel_edge_agent.link_presentation import (
    LinkPresentationRejectedError,
    OperatorLinkState,
    present_link_status,
)

ROOT = Path(__file__).parents[3]
SCHEMA = (
    ROOT
    / "packages"
    / "contracts"
    / "schemas"
    / "v1"
    / "tomato-link-status.schema.json"
)
NOW = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)


def load_schema() -> dict[str, Any]:
    with SCHEMA.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def transport(state: OutboundLinkState) -> OutboundLinkStatus:
    return OutboundLinkStatus(
        state=state,
        attempt=0,
        retry_at=None,
        last_heartbeat_at=NOW if state is OutboundLinkState.CONNECTED else None,
    )


def test_secure_requires_transport_session_credential_and_cancel_lane() -> None:
    view = present_link_status(
        transport(OutboundLinkState.CONNECTED),
        now=NOW,
        session_expires_at=NOW + timedelta(seconds=60),
        credential_revision=2,
        credential_revoked=False,
        cancellation_lane_ready=True,
    )
    contract = view.to_contract()

    assert view.state is OperatorLinkState.SECURE
    assert contract["indicator"] == "LINK: SECURE"
    assert contract["end_to_end_encrypted"] is True
    Draft202012Validator(
        load_schema(),
        format_checker=FormatChecker(),
    ).validate(contract)


@pytest.mark.parametrize(
    ("session_expires_at", "credential_revision", "cancel_ready"),
    [
        (None, 2, True),
        (NOW, 2, True),
        (NOW + timedelta(seconds=60), None, True),
        (NOW + timedelta(seconds=60), 2, False),
    ],
)
def test_open_websocket_is_degraded_without_every_security_control(
    session_expires_at: datetime | None,
    credential_revision: int | None,
    cancel_ready: bool,
) -> None:
    view = present_link_status(
        transport(OutboundLinkState.CONNECTED),
        now=NOW,
        session_expires_at=session_expires_at,
        credential_revision=credential_revision,
        credential_revoked=False,
        cancellation_lane_ready=cancel_ready,
    )

    assert view.state is OperatorLinkState.DEGRADED
    assert view.end_to_end_encrypted is False
    assert view.to_contract()["indicator"] == "LINK: DEGRADED"


def test_revocation_overrides_connected_transport_and_hides_secure_claim() -> None:
    view = present_link_status(
        transport(OutboundLinkState.CONNECTED),
        now=NOW,
        session_expires_at=NOW + timedelta(seconds=60),
        credential_revision=3,
        credential_revoked=True,
        cancellation_lane_ready=True,
    )

    assert view.state is OperatorLinkState.REVOKED
    assert view.end_to_end_encrypted is False
    assert view.to_contract()["indicator"] == "LINK: REVOKED"


@pytest.mark.parametrize(
    ("transport_state", "expected"),
    [
        (OutboundLinkState.DISCONNECTED, OperatorLinkState.DISCONNECTED),
        (OutboundLinkState.BACKOFF, OperatorLinkState.DISCONNECTED),
        (OutboundLinkState.CONNECTING, OperatorLinkState.CONNECTING),
        (OutboundLinkState.STOPPED, OperatorLinkState.STOPPED),
    ],
)
def test_non_connected_states_never_claim_encryption(
    transport_state: OutboundLinkState,
    expected: OperatorLinkState,
) -> None:
    view = present_link_status(
        transport(transport_state),
        now=NOW,
        session_expires_at=NOW + timedelta(seconds=60),
        credential_revision=1,
        credential_revoked=False,
        cancellation_lane_ready=True,
    )

    assert view.state is expected
    assert view.end_to_end_encrypted is False
    assert view.cancellation_lane_ready is False


def test_naive_status_time_is_rejected() -> None:
    with pytest.raises(LinkPresentationRejectedError) as rejected:
        present_link_status(
            transport(OutboundLinkState.CONNECTED),
            now=datetime(2026, 7, 29, 10, 0),
            session_expires_at=None,
            credential_revision=None,
            credential_revoked=False,
            cancellation_lane_ready=False,
        )

    assert rejected.value.reason_code == "LINK_STATUS_TIMEZONE_REQUIRED"

from datetime import UTC, datetime, timedelta

import pytest
from tomato_sentinel_edge_agent import (
    HEARTBEAT_TIMEOUT,
    MAXIMUM_CONNECT_ATTEMPTS,
    OutboundLinkRejectedError,
    OutboundLinkState,
    OutboundTomatoLinkClient,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def test_client_connects_and_accepts_monotonic_heartbeats() -> None:
    client = OutboundTomatoLinkClient()

    client.start(now=NOW)
    client.connected(now=NOW)
    client.heartbeat(now=NOW + timedelta(seconds=10))

    assert client.status.state is OutboundLinkState.CONNECTED
    assert client.status.last_heartbeat_at == NOW + timedelta(seconds=10)


def test_missed_heartbeat_enters_bounded_backoff() -> None:
    client = OutboundTomatoLinkClient()
    client.start(now=NOW)
    client.connected(now=NOW)

    client.tick(now=NOW + HEARTBEAT_TIMEOUT + timedelta(microseconds=1))

    assert client.status.state is OutboundLinkState.BACKOFF
    assert client.status.attempt == 1
    assert client.status.retry_at == NOW + HEARTBEAT_TIMEOUT + timedelta(
        seconds=1,
        microseconds=1,
    )


def test_backoff_does_not_retry_early() -> None:
    client = OutboundTomatoLinkClient()
    client.start(now=NOW)
    client.connection_failed(now=NOW)

    client.tick(now=NOW + timedelta(milliseconds=999))
    assert client.status.state is OutboundLinkState.BACKOFF

    client.tick(now=NOW + timedelta(seconds=1))
    assert client.status.state is OutboundLinkState.CONNECTING


def test_repeated_failures_stop_without_infinite_retry() -> None:
    client = OutboundTomatoLinkClient()
    current = NOW
    client.start(now=current)

    for attempt in range(MAXIMUM_CONNECT_ATTEMPTS):
        client.connection_failed(now=current)
        if attempt == MAXIMUM_CONNECT_ATTEMPTS - 1:
            break
        retry_at = client.status.retry_at
        assert retry_at is not None
        current = retry_at
        client.tick(now=current)

    assert client.status.state is OutboundLinkState.STOPPED
    assert client.status.retry_at is None


def test_stop_has_priority_over_later_tick() -> None:
    client = OutboundTomatoLinkClient()
    client.start(now=NOW)
    client.stop(now=NOW)

    client.tick(now=NOW + timedelta(hours=1))

    assert client.status.state is OutboundLinkState.STOPPED


def test_heartbeat_while_disconnected_is_denied() -> None:
    client = OutboundTomatoLinkClient()

    with pytest.raises(OutboundLinkRejectedError) as rejected:
        client.heartbeat(now=NOW)

    assert rejected.value.reason_code == "LINK_CLIENT_NOT_CONNECTED"


def test_naive_time_is_denied() -> None:
    client = OutboundTomatoLinkClient()

    with pytest.raises(OutboundLinkRejectedError) as rejected:
        client.start(now=datetime(2026, 7, 29, 12, 0))

    assert rejected.value.reason_code == "LINK_CLIENT_TIMEZONE_REQUIRED"

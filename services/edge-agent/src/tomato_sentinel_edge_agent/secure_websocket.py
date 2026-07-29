"""Fail-closed outbound WSS adapter for Tomato Link.

This adapter never discovers destinations and never accepts caller-supplied
proxy settings. Deployment configuration must provide an exact host allowlist,
a verifying TLS context and a credential through a separate provider.
"""

import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect

MAXIMUM_ACCESS_TOKEN_BYTES = 4_096
MAXIMUM_WIRE_MESSAGE_BYTES = 65_536
MAXIMUM_WIRE_QUEUE = 16
OPEN_TIMEOUT_SECONDS = 10
CLOSE_TIMEOUT_SECONDS = 5
PING_INTERVAL_SECONDS = 20
PING_TIMEOUT_SECONDS = 20

Connector = Callable[..., Awaitable[ClientConnection]]


class SecureWebSocketRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class RelayAccessCredential:
    __slots__ = ("_token",)

    def __init__(self, token: str) -> None:
        encoded = token.encode("utf-8")
        if (
            not encoded
            or len(encoded) > MAXIMUM_ACCESS_TOKEN_BYTES
            or "\r" in token
            or "\n" in token
        ):
            raise SecureWebSocketRejectedError("LINK_CREDENTIAL_INVALID")
        self._token = token

    def __repr__(self) -> str:
        return "RelayAccessCredential(token=<redacted>)"

    def authorization_header(self) -> str:
        return f"Bearer {self._token}"


@dataclass(frozen=True, slots=True)
class SecureWebSocketSettings:
    uri: str
    tls_context: ssl.SSLContext
    allowed_hosts: frozenset[str]

    def __post_init__(self) -> None:
        parsed = urlsplit(self.uri)
        host = parsed.hostname
        if (
            parsed.scheme != "wss"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise SecureWebSocketRejectedError("LINK_WSS_URI_INVALID")
        if host.lower() not in {item.lower() for item in self.allowed_hosts}:
            raise SecureWebSocketRejectedError("LINK_WSS_HOST_DENIED")
        if (
            not self.tls_context.check_hostname
            or self.tls_context.verify_mode is not ssl.CERT_REQUIRED
            or self.tls_context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            raise SecureWebSocketRejectedError("LINK_TLS_CONTEXT_INSECURE")


async def connect_secure_websocket(
    settings: SecureWebSocketSettings,
    credential: RelayAccessCredential,
    *,
    connector: Connector = connect,
) -> ClientConnection:
    """Open one bounded outbound connection with proxy discovery disabled."""

    kwargs: dict[str, Any] = {
        "additional_headers": {
            "Authorization": credential.authorization_header(),
        },
        "close_timeout": CLOSE_TIMEOUT_SECONDS,
        "compression": None,
        "max_queue": MAXIMUM_WIRE_QUEUE,
        "max_size": MAXIMUM_WIRE_MESSAGE_BYTES,
        "open_timeout": OPEN_TIMEOUT_SECONDS,
        "ping_interval": PING_INTERVAL_SECONDS,
        "ping_timeout": PING_TIMEOUT_SECONDS,
        "proxy": None,
        "ssl": settings.tls_context,
    }
    return await connector(settings.uri, **kwargs)

import asyncio
import ipaddress
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from tomato_sentinel_edge_agent.secure_websocket import (
    RelayAccessCredential,
    SecureWebSocketRejectedError,
    SecureWebSocketSettings,
    connect_secure_websocket,
)
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.server import ServerConnection, serve


def secure_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def settings(**changes: object) -> SecureWebSocketSettings:
    values: dict[str, object] = {
        "uri": "wss://relay.example.invalid/v1/link",
        "tls_context": secure_context(),
        "allowed_hosts": frozenset({"relay.example.invalid"}),
    }
    values.update(changes)
    return SecureWebSocketSettings(**values)  # type: ignore[arg-type]


def test_exact_wss_destination_and_verifying_tls_are_accepted() -> None:
    configured = settings()

    assert configured.uri == "wss://relay.example.invalid/v1/link"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"uri": "ws://relay.example.invalid/v1/link"}, "LINK_WSS_URI_INVALID"),
        (
            {"uri": "wss://user:secret@relay.example.invalid/v1/link"},
            "LINK_WSS_URI_INVALID",
        ),
        ({"uri": "wss://evil.example.invalid/v1/link"}, "LINK_WSS_HOST_DENIED"),
    ],
)
def test_unsafe_or_unapproved_destination_is_denied(
    change: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(SecureWebSocketRejectedError) as rejected:
        settings(**change)

    assert rejected.value.reason_code == reason


def test_non_verifying_tls_context_is_denied() -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with pytest.raises(SecureWebSocketRejectedError) as rejected:
        settings(tls_context=context)

    assert rejected.value.reason_code == "LINK_TLS_CONTEXT_INSECURE"


def test_connection_has_bounds_and_disables_ambient_proxy() -> None:
    captured: dict[str, Any] = {}
    sentinel = cast(ClientConnection, object())

    async def fake_connector(uri: str, **kwargs: object) -> ClientConnection:
        captured["uri"] = uri
        captured.update(kwargs)
        return sentinel

    result = asyncio.run(
        connect_secure_websocket(
            settings(),
            RelayAccessCredential("synthetic-test-token"),
            connector=fake_connector,
        )
    )

    assert result is sentinel
    assert captured["proxy"] is None
    assert captured["compression"] is None
    assert captured["max_size"] == 65_536
    assert captured["max_queue"] == 16
    assert captured["additional_headers"] == {
        "Authorization": "Bearer synthetic-test-token"
    }


def test_credentials_reject_header_injection_and_redact_repr() -> None:
    with pytest.raises(SecureWebSocketRejectedError) as rejected:
        RelayAccessCredential("value\r\nX-Forged: yes")

    credential = RelayAccessCredential("do-not-log-me")
    assert rejected.value.reason_code == "LINK_CREDENTIAL_INVALID"
    assert "do-not-log-me" not in repr(credential)


def ephemeral_tls_contexts(tmp_path: Path) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(minutes=5))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    certificate_path = tmp_path / "loopback-cert.pem"
    key_path = tmp_path / "loopback-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(certificate_path, key_path)
    client_context = ssl.create_default_context(cafile=str(certificate_path))
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    return server_context, client_context


@pytest.mark.loopback_network
def test_real_wss_loopback_uses_tls_and_authorization(tmp_path: Path) -> None:
    server_context, client_context = ephemeral_tls_contexts(tmp_path)

    async def scenario() -> None:
        async def handler(connection: ServerConnection) -> None:
            assert (
                connection.request.headers["Authorization"] == "Bearer loopback-token"
            )
            await connection.send("ready")

        async with serve(
            handler,
            "127.0.0.1",
            0,
            ssl=server_context,
            compression=None,
            max_size=65_536,
            max_queue=16,
        ) as server:
            port = server.sockets[0].getsockname()[1]
            connection = await connect_secure_websocket(
                SecureWebSocketSettings(
                    uri=f"wss://127.0.0.1:{port}/v1/link",
                    tls_context=client_context,
                    allowed_hosts=frozenset({"127.0.0.1"}),
                ),
                RelayAccessCredential("loopback-token"),
            )
            async with connection:
                assert await connection.recv() == "ready"

    asyncio.run(scenario())

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from tomato_sentinel_link_relay import (
    GovernedTomatoLinkCodec,
    InMemoryLinkCredentialVault,
    LinkCredentialState,
    LinkRoute,
    LinkSessionAuthority,
    LinkSessionRejectedError,
    ManagedLinkSession,
    TomatoLinkBinding,
    TomatoLinkSealedPayloadCodec,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
ROUTE = LinkRoute(
    organization_id="organization:01",
    source_endpoint_id="cardputer:01",
    destination_endpoint_id="edge:home-01",
)
ROOT_SECRET = b"link-root-secret-separate-from-device-auth"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def vault(secret: bytes = ROOT_SECRET) -> InMemoryLinkCredentialVault:
    result = InMemoryLinkCredentialVault()
    result.provision(ROUTE, key_id="link-root-key:01", secret=secret)
    return result


def authority(
    credential_vault: InMemoryLinkCredentialVault,
    salt: bytes = b"\x21" * 32,
) -> LinkSessionAuthority:
    return LinkSessionAuthority(
        load_json(SCHEMAS / "tomato-link-session-lease.schema.json"),
        credential_vault,
        salt_source=lambda _: salt,
    )


def issue(
    session_authority: LinkSessionAuthority,
    *,
    lease_id: str = "link-lease:01",
    session_id: str = "link-session:01",
) -> ManagedLinkSession:
    return session_authority.issue(
        lease_id=lease_id,
        session_id=session_id,
        route=ROUTE,
        now=NOW,
        ttl=timedelta(seconds=60),
    )


def binding() -> TomatoLinkBinding:
    return TomatoLinkBinding(
        frame_id="link-frame:01",
        organization_id=ROUTE.organization_id,
        source_endpoint_id=ROUTE.source_endpoint_id,
        destination_endpoint_id=ROUTE.destination_endpoint_id,
        session_id="link-session:01",
        sequence=1,
        created_at="2026-07-29T08:00:00Z",
        expires_at="2026-07-29T08:01:00Z",
    )


def test_two_endpoints_derive_same_short_lived_session_key() -> None:
    device_vault = vault()
    edge_vault = vault()
    issued = issue(authority(device_vault))
    accepted = authority(edge_vault).accept(
        issued.lease_contract,
        received_at=NOW,
    )
    codec = TomatoLinkSealedPayloadCodec(
        load_json(SCHEMAS / "tomato-link-sealed-payload.schema.json"),
        nonce_source=lambda _: b"\x22" * 12,
    )

    sealed = GovernedTomatoLinkCodec(codec, device_vault).seal(
        b"signed-device-envelope",
        binding=binding(),
        session=issued,
        now=NOW,
    )
    opened = GovernedTomatoLinkCodec(codec, edge_vault).open(
        sealed,
        binding=binding(),
        session=accepted,
        now=NOW,
    )

    assert opened == b"signed-device-envelope"
    assert issued.lease.expires_at == NOW + timedelta(seconds=60)
    assert ROOT_SECRET.decode() not in repr(issued)
    assert "<redacted>" in repr(issued)


def test_returned_lease_contract_cannot_mutate_managed_session() -> None:
    issued = issue(authority(vault()))
    caller_copy = cast(dict[str, object], issued.lease_contract)
    caller_copy["session_id"] = "link-session:mutated"
    cast(dict[str, object], caller_copy["authentication"])["tag"] = "f" * 64

    assert issued.lease_contract["session_id"] == "link-session:01"
    authentication = cast(
        dict[str, object],
        issued.lease_contract["authentication"],
    )
    assert authentication["tag"] != "f" * 64


def test_lease_tampering_is_rejected_before_acceptance_state() -> None:
    receiver = authority(vault())
    issued = issue(authority(vault()))
    tampered = dict(issued.lease_contract)
    tampered["session_id"] = "link-session:tampered"

    with pytest.raises(LinkSessionRejectedError) as rejected:
        receiver.accept(tampered, received_at=NOW)
    accepted = receiver.accept(issued.lease_contract, received_at=NOW)

    assert rejected.value.reason_code == "LINK_SESSION_AUTHENTICATION_INVALID"
    assert accepted.lease.session_id == "link-session:01"


def test_exact_issue_retry_is_idempotent_but_changed_lease_id_reuse_is_denied() -> None:
    session_authority = authority(vault())
    first = issue(session_authority)
    retry = issue(session_authority)

    with pytest.raises(LinkSessionRejectedError) as rejected:
        issue(session_authority, session_id="link-session:changed")

    assert retry is first
    assert rejected.value.reason_code == "LINK_SESSION_LEASE_ID_REUSED"


@pytest.mark.parametrize(
    "ttl",
    [timedelta(seconds=9), timedelta(seconds=121)],
)
def test_unbounded_session_ttl_is_denied(ttl: timedelta) -> None:
    with pytest.raises(LinkSessionRejectedError) as rejected:
        authority(vault()).issue(
            lease_id="link-lease:01",
            session_id="link-session:01",
            route=ROUTE,
            now=NOW,
            ttl=ttl,
        )

    assert rejected.value.reason_code == "LINK_SESSION_TTL_INVALID"


def test_expired_session_is_denied() -> None:
    credential_vault = vault()
    issued = issue(authority(credential_vault))

    with pytest.raises(LinkSessionRejectedError) as rejected:
        credential_vault.require_session_active(
            issued,
            now=NOW + timedelta(seconds=60),
        )

    assert rejected.value.reason_code == "LINK_SESSION_EXPIRED"


def test_rotation_invalidates_old_session_and_changes_derived_key() -> None:
    credential_vault = vault()
    session_authority = authority(credential_vault)
    old = issue(session_authority)
    status = credential_vault.rotate(
        ROUTE,
        expected_key_id="link-root-key:01",
        new_key_id="link-root-key:02",
        new_secret=b"rotated-link-root-secret-separate-32-bytes",
    )

    with pytest.raises(LinkSessionRejectedError) as rejected:
        credential_vault.require_session_active(old, now=NOW)
    new = session_authority.issue(
        lease_id="link-lease:02",
        session_id="link-session:02",
        route=ROUTE,
        now=NOW,
        ttl=timedelta(seconds=60),
    )

    assert status.identity_revision == 2
    assert new.lease.key_id == "link-root-key:02"
    assert rejected.value.reason_code == "LINK_SESSION_IDENTITY_STALE"


def test_revocation_immediately_invalidates_existing_session() -> None:
    credential_vault = vault()
    issued = issue(authority(credential_vault))
    status = credential_vault.revoke(
        ROUTE,
        expected_key_id="link-root-key:01",
    )

    with pytest.raises(LinkSessionRejectedError) as rejected:
        credential_vault.require_session_active(issued, now=NOW)

    assert status.state is LinkCredentialState.REVOKED
    assert rejected.value.reason_code == "LINK_CREDENTIAL_REVOKED"


def test_revocation_is_checked_again_before_decryption() -> None:
    device_vault = vault()
    edge_vault = vault()
    issued = issue(authority(device_vault))
    accepted = authority(edge_vault).accept(
        issued.lease_contract,
        received_at=NOW,
    )
    codec = TomatoLinkSealedPayloadCodec(
        load_json(SCHEMAS / "tomato-link-sealed-payload.schema.json"),
        nonce_source=lambda _: b"\x23" * 12,
    )
    sealed = GovernedTomatoLinkCodec(codec, device_vault).seal(
        b"sensitive",
        binding=binding(),
        session=issued,
        now=NOW,
    )
    edge_vault.revoke(ROUTE, expected_key_id="link-root-key:01")

    with pytest.raises(LinkSessionRejectedError) as rejected:
        GovernedTomatoLinkCodec(codec, edge_vault).open(
            sealed,
            binding=binding(),
            session=accepted,
            now=NOW,
        )

    assert rejected.value.reason_code == "LINK_CREDENTIAL_REVOKED"


def test_root_secrets_are_unique_and_never_exposed_in_status() -> None:
    credential_vault = vault()
    other_route = LinkRoute(
        organization_id="organization:01",
        source_endpoint_id="cardputer:02",
        destination_endpoint_id="edge:home-01",
    )

    with pytest.raises(LinkSessionRejectedError) as reused:
        credential_vault.provision(
            other_route,
            key_id="link-root-key:02",
            secret=ROOT_SECRET,
        )
    with pytest.raises(LinkSessionRejectedError) as short:
        InMemoryLinkCredentialVault().provision(
            ROUTE,
            key_id="link-root-key:01",
            secret=b"short",
        )

    status = credential_vault.status(ROUTE)
    assert reused.value.reason_code == "LINK_CREDENTIAL_SECRET_REUSED"
    assert short.value.reason_code == "LINK_CREDENTIAL_SECRET_TOO_SHORT"
    assert ROOT_SECRET.decode() not in repr(status)

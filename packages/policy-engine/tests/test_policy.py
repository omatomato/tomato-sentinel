from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from tomato_sentinel_policy import (
    ActorContext,
    AuthorizationKind,
    Confirmation,
    ConfirmationMethod,
    Decision,
    DeviceContext,
    OperationScope,
    PolicyRequest,
    Profile,
    ReasonCode,
    ResourceGrant,
    RiskClass,
    ToolManifest,
    ToolRegistry,
    TrustState,
    evaluate,
)

NOW = datetime(2026, 7, 25, 18, 40, tzinfo=UTC)
CAMERA_PLAN_HASH = f"sha256:{'a' * 64}"
ACTIVE_PLAN_HASH = f"sha256:{'b' * 64}"


def camera_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="camera.monitor",
        version=1,
        risk_class=RiskClass.R1,
        required_profile=Profile.SENTINEL,
        authorization_kind=AuthorizationKind.RESOURCE_GRANT,
        required_roles=frozenset({"operator"}),
        required_capabilities=frozenset({"camera_monitoring"}),
        maximum_duration_seconds=300,
    )


def active_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="network.targeted_validation",
        version=1,
        risk_class=RiskClass.R2,
        required_profile=Profile.LAB,
        authorization_kind=AuthorizationKind.OPERATION_SCOPE,
        required_roles=frozenset({"security_operator"}),
        required_capabilities=frozenset({"network_validation"}),
        requires_confirmation=True,
        requires_physical_confirmation=True,
        maximum_duration_seconds=60,
    )


def registry_with(*manifests: ToolManifest) -> ToolRegistry:
    registry = ToolRegistry()
    for manifest in manifests:
        registry.register(manifest)
    return registry


def camera_grant() -> ResourceGrant:
    return ResourceGrant(
        organization_id="org:01",
        resource_ids=frozenset({"camera:garage-01"}),
        valid_until=NOW + timedelta(minutes=10),
    )


def camera_request() -> PolicyRequest:
    return PolicyRequest(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"operator"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"camera_monitoring"}),
        ),
        profile=Profile.SENTINEL,
        tool_id="camera.monitor",
        tool_version=1,
        targets=("camera:garage-01",),
        parameters={"duration_seconds": 120},
        evaluated_at=NOW,
        plan_hash=CAMERA_PLAN_HASH,
        resource_grant=camera_grant(),
    )


def active_scope() -> OperationScope:
    return OperationScope(
        scope_id="scope:lab-01",
        organization_id="org:01",
        tool_ids=frozenset({"network.targeted_validation"}),
        target_ids=frozenset({"host:lab-01"}),
        valid_until=NOW + timedelta(minutes=5),
    )


def active_request() -> PolicyRequest:
    return PolicyRequest(
        actor=ActorContext(
            actor_id="user:01",
            organization_id="org:01",
            roles=frozenset({"security_operator"}),
        ),
        device=DeviceContext(
            device_id="cardputer:01",
            organization_id="org:01",
            trust_state=TrustState.TRUSTED,
            capabilities=frozenset({"network_validation"}),
        ),
        profile=Profile.LAB,
        tool_id="network.targeted_validation",
        tool_version=1,
        targets=("host:lab-01",),
        parameters={"duration_seconds": 30},
        evaluated_at=NOW,
        plan_hash=ACTIVE_PLAN_HASH,
        operation_scope=active_scope(),
    )


def test_authorized_camera_monitoring_is_allowed() -> None:
    decision = evaluate(camera_request(), registry_with(camera_manifest()))

    assert decision.decision is Decision.ALLOW
    assert decision.reason_code is ReasonCode.AUTHORIZED
    assert decision.obligations[0].parameters["maximum_duration_seconds"] == 300


@pytest.mark.parametrize(
    ("policy_request", "reason"),
    [
        (
            replace(
                camera_request(),
                actor=replace(camera_request().actor, organization_id="org:other"),
            ),
            ReasonCode.ORGANIZATION_MISMATCH,
        ),
        (
            replace(
                camera_request(),
                device=replace(
                    camera_request().device,
                    trust_state=TrustState.REVOKED,
                ),
            ),
            ReasonCode.DEVICE_NOT_TRUSTED,
        ),
        (
            replace(camera_request(), profile=Profile.ASSISTANT),
            ReasonCode.PROFILE_REQUIRED,
        ),
        (
            replace(
                camera_request(),
                actor=replace(camera_request().actor, roles=frozenset()),
            ),
            ReasonCode.ACTOR_ROLE_REQUIRED,
        ),
        (
            replace(
                camera_request(),
                device=replace(camera_request().device, capabilities=frozenset()),
            ),
            ReasonCode.CAPABILITY_REQUIRED,
        ),
        (
            replace(camera_request(), resource_grant=None),
            ReasonCode.GRANT_REQUIRED,
        ),
        (
            replace(
                camera_request(),
                resource_grant=replace(camera_grant(), valid_until=NOW),
            ),
            ReasonCode.GRANT_EXPIRED,
        ),
        (
            replace(camera_request(), targets=("camera:unauthorized",)),
            ReasonCode.TARGET_NOT_AUTHORIZED,
        ),
        (
            replace(camera_request(), parameters={"duration_seconds": 0}),
            ReasonCode.DURATION_INVALID,
        ),
        (
            replace(camera_request(), parameters={"duration_seconds": 301}),
            ReasonCode.DURATION_LIMIT_EXCEEDED,
        ),
    ],
)
def test_camera_denials_have_stable_reasons(
    policy_request: PolicyRequest,
    reason: ReasonCode,
) -> None:
    decision = evaluate(policy_request, registry_with(camera_manifest()))

    assert decision.decision is not Decision.ALLOW
    assert decision.reason_code is reason


def test_unknown_tool_is_denied() -> None:
    decision = evaluate(camera_request(), ToolRegistry())

    assert decision.decision is Decision.DENY
    assert decision.reason_code is ReasonCode.TOOL_NOT_FOUND


def test_active_operation_requires_scope() -> None:
    request = replace(active_request(), operation_scope=None)

    decision = evaluate(request, registry_with(active_manifest()))

    assert decision.decision is Decision.REQUIRE_SCOPE
    assert decision.reason_code is ReasonCode.SCOPE_REQUIRED


@pytest.mark.parametrize(
    ("scope", "reason"),
    [
        (
            replace(active_scope(), valid_until=NOW),
            ReasonCode.SCOPE_EXPIRED,
        ),
        (
            replace(active_scope(), tool_ids=frozenset()),
            ReasonCode.TOOL_NOT_AUTHORIZED,
        ),
        (
            replace(active_scope(), target_ids=frozenset()),
            ReasonCode.TARGET_NOT_AUTHORIZED,
        ),
    ],
)
def test_invalid_scope_is_denied(
    scope: OperationScope,
    reason: ReasonCode,
) -> None:
    decision = evaluate(
        replace(active_request(), operation_scope=scope),
        registry_with(active_manifest()),
    )

    assert decision.decision is Decision.DENY
    assert decision.reason_code is reason


def test_empty_target_set_is_denied() -> None:
    decision = evaluate(
        replace(camera_request(), targets=()),
        registry_with(camera_manifest()),
    )

    assert decision.decision is Decision.DENY
    assert decision.reason_code is ReasonCode.TARGET_COUNT_INVALID


def test_active_operation_requires_physical_confirmation() -> None:
    request = active_request()
    registry = registry_with(active_manifest())

    preview = evaluate(request, registry)

    assert preview.decision is Decision.ALLOW_WITH_CONFIRMATION
    assert preview.obligations[0].parameters["method"] == "physical"

    operator_confirmation = Confirmation(
        actor_id=request.actor.actor_id,
        device_id=request.device.device_id,
        plan_hash=request.plan_hash,
        method=ConfirmationMethod.OPERATOR,
        valid_until=NOW + timedelta(seconds=30),
    )
    wrong_method = evaluate(
        replace(request, confirmation=operator_confirmation),
        registry,
    )

    assert wrong_method.decision is Decision.REQUIRE_PHYSICAL_CONFIRMATION

    physical_confirmation = replace(
        operator_confirmation,
        method=ConfirmationMethod.PHYSICAL,
    )
    allowed = evaluate(replace(request, confirmation=physical_confirmation), registry)

    assert allowed.decision is Decision.ALLOW


def test_changed_plan_cannot_reuse_confirmation() -> None:
    request = active_request()
    confirmation = Confirmation(
        actor_id=request.actor.actor_id,
        device_id=request.device.device_id,
        plan_hash=f"sha256:{'c' * 64}",
        method=ConfirmationMethod.PHYSICAL,
        valid_until=NOW + timedelta(seconds=30),
    )

    decision = evaluate(
        replace(request, confirmation=confirmation),
        registry_with(active_manifest()),
    )

    assert decision.decision is Decision.DENY
    assert decision.reason_code is ReasonCode.CONFIRMATION_MISMATCH


def test_expired_confirmation_is_denied() -> None:
    request = active_request()
    confirmation = Confirmation(
        actor_id=request.actor.actor_id,
        device_id=request.device.device_id,
        plan_hash=request.plan_hash,
        method=ConfirmationMethod.PHYSICAL,
        valid_until=NOW,
    )

    decision = evaluate(
        replace(request, confirmation=confirmation),
        registry_with(active_manifest()),
    )

    assert decision.decision is Decision.DENY
    assert decision.reason_code is ReasonCode.CONFIRMATION_EXPIRED


def test_r3_manifest_cannot_be_registered() -> None:
    manifest = replace(camera_manifest(), risk_class=RiskClass.R3)

    with pytest.raises(ValueError, match="R3 tools cannot be registered"):
        registry_with(manifest)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            replace(
                active_manifest(),
                requires_confirmation=False,
                requires_physical_confirmation=True,
            ),
            "physical confirmation requires confirmation",
        ),
        (
            replace(active_manifest(), maximum_duration_seconds=None),
            "R1 and R2 tools require a maximum duration",
        ),
        (
            replace(
                active_manifest(),
                authorization_kind=AuthorizationKind.RESOURCE_GRANT,
            ),
            "R2 tools require an operation scope",
        ),
        (
            replace(
                active_manifest(),
                requires_confirmation=False,
                requires_physical_confirmation=False,
            ),
            "R2 tools require confirmation",
        ),
        (
            replace(active_manifest(), required_roles=frozenset()),
            "R2 tools require an operator role",
        ),
    ],
)
def test_invalid_sensitive_manifests_are_rejected(
    manifest: ToolManifest,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        registry_with(manifest)

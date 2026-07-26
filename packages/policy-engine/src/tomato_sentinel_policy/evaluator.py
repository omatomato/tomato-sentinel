"""Side-effect-free policy evaluation."""

from .models import (
    AuthorizationKind,
    ConfirmationMethod,
    Decision,
    Obligation,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    TrustState,
)
from .registry import ToolNotFoundError, ToolRegistry


def _deny(reason_code: ReasonCode) -> PolicyDecision:
    return PolicyDecision(decision=Decision.DENY, reason_code=reason_code)


def evaluate(request: PolicyRequest, registry: ToolRegistry) -> PolicyDecision:
    """Evaluate one immutable request without consulting external state."""
    try:
        tool = registry.get(request.tool_id, request.tool_version)
    except ToolNotFoundError:
        return _deny(ReasonCode.TOOL_NOT_FOUND)

    if (
        request.actor.organization_id != request.device.organization_id
        or (
            request.resource_grant is not None
            and request.actor.organization_id != request.resource_grant.organization_id
        )
        or (
            request.operation_scope is not None
            and request.actor.organization_id != request.operation_scope.organization_id
        )
    ):
        return _deny(ReasonCode.ORGANIZATION_MISMATCH)

    if request.device.trust_state is not TrustState.TRUSTED:
        return _deny(ReasonCode.DEVICE_NOT_TRUSTED)

    if request.profile is not tool.required_profile:
        return PolicyDecision(
            decision=Decision.REQUIRE_PROFILE_CHANGE,
            reason_code=ReasonCode.PROFILE_REQUIRED,
        )

    if not tool.required_roles.issubset(request.actor.roles):
        return _deny(ReasonCode.ACTOR_ROLE_REQUIRED)

    if not tool.required_capabilities.issubset(request.device.capabilities):
        return _deny(ReasonCode.CAPABILITY_REQUIRED)

    if not request.targets or len(request.targets) > tool.maximum_targets:
        return _deny(ReasonCode.TARGET_COUNT_INVALID)

    authorization_decision = _authorize_targets(request, tool.authorization_kind)
    if authorization_decision is not None:
        return authorization_decision

    duration_decision = _validate_duration(
        request.parameters.get("duration_seconds"),
        tool.maximum_duration_seconds,
    )
    if duration_decision is not None:
        return duration_decision

    if tool.requires_confirmation:
        confirmation_decision = _validate_confirmation(
            request,
            requires_physical=tool.requires_physical_confirmation,
        )
        if confirmation_decision is not None:
            return confirmation_decision

    obligations: list[Obligation] = []
    if tool.maximum_duration_seconds is not None:
        obligations.append(
            Obligation(
                obligation_type="execution_limit",
                parameters={
                    "maximum_duration_seconds": tool.maximum_duration_seconds,
                    "maximum_targets": tool.maximum_targets,
                },
            )
        )

    return PolicyDecision(
        decision=Decision.ALLOW,
        reason_code=ReasonCode.AUTHORIZED,
        obligations=tuple(obligations),
    )


def _authorize_targets(
    request: PolicyRequest,
    authorization_kind: AuthorizationKind,
) -> PolicyDecision | None:
    if authorization_kind is AuthorizationKind.NONE:
        return None

    if authorization_kind is AuthorizationKind.RESOURCE_GRANT:
        grant = request.resource_grant
        if grant is None:
            return _deny(ReasonCode.GRANT_REQUIRED)
        if not grant.enabled:
            return _deny(ReasonCode.GRANT_DISABLED)
        if grant.valid_until <= request.evaluated_at:
            return _deny(ReasonCode.GRANT_EXPIRED)
        if not set(request.targets).issubset(grant.resource_ids):
            return _deny(ReasonCode.TARGET_NOT_AUTHORIZED)
        return None

    scope = request.operation_scope
    if scope is None:
        return PolicyDecision(
            decision=Decision.REQUIRE_SCOPE,
            reason_code=ReasonCode.SCOPE_REQUIRED,
        )
    if scope.valid_until <= request.evaluated_at:
        return _deny(ReasonCode.SCOPE_EXPIRED)
    if request.tool_id not in scope.tool_ids:
        return _deny(ReasonCode.TOOL_NOT_AUTHORIZED)
    if not set(request.targets).issubset(scope.target_ids):
        return _deny(ReasonCode.TARGET_NOT_AUTHORIZED)
    return None


def _validate_duration(
    duration: object,
    maximum_duration_seconds: int | None,
) -> PolicyDecision | None:
    if maximum_duration_seconds is None:
        return None
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
        return _deny(ReasonCode.DURATION_INVALID)
    if duration > maximum_duration_seconds:
        return _deny(ReasonCode.DURATION_LIMIT_EXCEEDED)
    return None


def _validate_confirmation(
    request: PolicyRequest,
    *,
    requires_physical: bool,
) -> PolicyDecision | None:
    confirmation = request.confirmation
    if confirmation is None:
        return PolicyDecision(
            decision=Decision.ALLOW_WITH_CONFIRMATION,
            reason_code=ReasonCode.AUTHORIZED_CONFIRMATION_REQUIRED,
            obligations=(
                Obligation(
                    obligation_type="confirmation",
                    parameters={
                        "plan_hash": request.plan_hash,
                        "method": (
                            ConfirmationMethod.PHYSICAL
                            if requires_physical
                            else ConfirmationMethod.OPERATOR
                        ),
                    },
                ),
            ),
        )
    if confirmation.valid_until <= request.evaluated_at:
        return _deny(ReasonCode.CONFIRMATION_EXPIRED)
    if (
        confirmation.actor_id != request.actor.actor_id
        or confirmation.device_id != request.device.device_id
        or confirmation.plan_hash != request.plan_hash
    ):
        return _deny(ReasonCode.CONFIRMATION_MISMATCH)

    if requires_physical and confirmation.method is not ConfirmationMethod.PHYSICAL:
        return PolicyDecision(
            decision=Decision.REQUIRE_PHYSICAL_CONFIRMATION,
            reason_code=ReasonCode.AUTHORIZED_CONFIRMATION_REQUIRED,
        )
    return None

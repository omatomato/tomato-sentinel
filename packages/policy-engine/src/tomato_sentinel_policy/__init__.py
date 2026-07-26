"""Deterministic authorization primitives for Tomato Sentinel."""

from .evaluator import evaluate
from .models import (
    ActorContext,
    AuthorizationKind,
    Confirmation,
    ConfirmationMethod,
    Decision,
    DeviceContext,
    Obligation,
    OperationScope,
    PolicyDecision,
    PolicyRequest,
    Profile,
    ReasonCode,
    ResourceGrant,
    RiskClass,
    ToolManifest,
    TrustState,
)
from .registry import ToolNotFoundError, ToolRegistry

__all__ = [
    "ActorContext",
    "AuthorizationKind",
    "Confirmation",
    "ConfirmationMethod",
    "Decision",
    "DeviceContext",
    "Obligation",
    "OperationScope",
    "PolicyDecision",
    "PolicyRequest",
    "Profile",
    "ReasonCode",
    "ResourceGrant",
    "RiskClass",
    "ToolManifest",
    "ToolNotFoundError",
    "ToolRegistry",
    "TrustState",
    "evaluate",
]

"""Explicit versioned tool registry."""

from .models import AuthorizationKind, RiskClass, ToolManifest


class ToolNotFoundError(LookupError):
    """Raised when an exact tool ID and version are not registered."""


class ToolRegistry:
    """In-memory registry with deterministic duplicate and R3 rejection."""

    def __init__(self) -> None:
        self._tools: dict[tuple[str, int], ToolManifest] = {}

    def register(self, manifest: ToolManifest) -> None:
        if manifest.risk_class is RiskClass.R3:
            raise ValueError("R3 tools cannot be registered")
        if (
            manifest.requires_physical_confirmation
            and not manifest.requires_confirmation
        ):
            raise ValueError("physical confirmation requires confirmation")
        if manifest.risk_class in {RiskClass.R1, RiskClass.R2} and (
            manifest.maximum_duration_seconds is None
        ):
            raise ValueError("R1 and R2 tools require a maximum duration")
        if manifest.risk_class is RiskClass.R2:
            if manifest.authorization_kind is not AuthorizationKind.OPERATION_SCOPE:
                raise ValueError("R2 tools require an operation scope")
            if not manifest.requires_confirmation:
                raise ValueError("R2 tools require confirmation")
            if not manifest.required_roles:
                raise ValueError("R2 tools require an operator role")
        if not manifest.tool_id:
            raise ValueError("tool_id cannot be empty")
        if manifest.version < 1:
            raise ValueError("tool version must be positive")
        if manifest.maximum_targets < 1:
            raise ValueError("maximum_targets must be positive")
        if (
            manifest.maximum_duration_seconds is not None
            and manifest.maximum_duration_seconds < 1
        ):
            raise ValueError("maximum duration must be positive")

        key = (manifest.tool_id, manifest.version)
        if key in self._tools:
            raise ValueError(f"tool already registered: {key!r}")
        self._tools[key] = manifest

    def get(self, tool_id: str, version: int) -> ToolManifest:
        try:
            return self._tools[(tool_id, version)]
        except KeyError as error:
            raise ToolNotFoundError((tool_id, version)) from error

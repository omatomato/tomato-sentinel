"""Closed simulated menu for composing registered structured commands."""

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

_TYPED_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")
MAXIMUM_MENU_CAMERAS = 32
MAXIMUM_MENU_INVENTORIES = 8
MAXIMUM_MENU_NETWORKS = 8


class CommandCompositionRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class CameraMenuEntry:
    camera_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class InventoryMenuEntry:
    inventory_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class NetworkMenuEntry:
    network_id: str
    display_name: str
    interface_id: str


@dataclass(frozen=True, slots=True)
class CommandMenuAction:
    action: str
    label: str
    profile: str
    risk_class: str


class RegisteredCommandComposer:
    """Build commands from fixed actions and preloaded non-authoritative targets."""

    _ACTIONS = (
        CommandMenuAction(
            action="camera.status",
            label="Camera status",
            profile="assistant",
            risk_class="R0",
        ),
        CommandMenuAction(
            action="camera.monitor",
            label="Monitor camera",
            profile="sentinel",
            risk_class="R1",
        ),
        CommandMenuAction(
            action="asset.list",
            label="Asset inventory",
            profile="inventory",
            risk_class="R0",
        ),
        CommandMenuAction(
            action="network.passive_discovery",
            label="Passive discovery",
            profile="inventory",
            risk_class="R1",
        ),
    )

    def __init__(
        self,
        *,
        actor_id: str,
        organization_id: str,
        device_id: str,
        cameras: tuple[CameraMenuEntry, ...],
        inventories: tuple[InventoryMenuEntry, ...] = (),
        networks: tuple[NetworkMenuEntry, ...] = (),
    ) -> None:
        _require_typed_id(actor_id)
        _require_typed_id(organization_id)
        _require_typed_id(device_id)
        if len(cameras) > MAXIMUM_MENU_CAMERAS:
            raise ValueError("camera menu size is invalid")
        camera_ids: set[str] = set()
        for camera in cameras:
            _require_typed_id(camera.camera_id)
            if not camera.display_name or len(camera.display_name) > 120:
                raise ValueError("camera display name is invalid")
            if camera.camera_id in camera_ids:
                raise ValueError("camera menu contains a duplicate target")
            camera_ids.add(camera.camera_id)
        self._actor_id = actor_id
        self._organization_id = organization_id
        self._device_id = device_id
        self._cameras = cameras
        self._camera_ids = frozenset(camera_ids)
        if len(inventories) > MAXIMUM_MENU_INVENTORIES:
            raise ValueError("inventory menu size is invalid")
        inventory_ids: set[str] = set()
        for inventory in inventories:
            _require_typed_id(inventory.inventory_id)
            if not inventory.display_name or len(inventory.display_name) > 120:
                raise ValueError("inventory display name is invalid")
            if inventory.inventory_id in inventory_ids:
                raise ValueError("inventory menu contains a duplicate target")
            inventory_ids.add(inventory.inventory_id)
        self._inventories = inventories
        self._inventory_ids = frozenset(inventory_ids)
        if len(networks) > MAXIMUM_MENU_NETWORKS:
            raise ValueError("network menu size is invalid")
        network_ids: set[str] = set()
        for network in networks:
            _require_typed_id(network.network_id)
            _require_typed_id(network.interface_id)
            if not network.display_name or len(network.display_name) > 120:
                raise ValueError("network display name is invalid")
            if network.network_id in network_ids:
                raise ValueError("network menu contains a duplicate target")
            network_ids.add(network.network_id)
        self._networks = networks
        self._network_interfaces = {
            network.network_id: network.interface_id for network in networks
        }
        if not self._camera_ids and not self._inventory_ids and not network_ids:
            raise ValueError("command menu requires at least one target")

    @property
    def actions(self) -> tuple[CommandMenuAction, ...]:
        return tuple(
            action
            for action in self._ACTIONS
            if (
                (action.action == "asset.list" and self._inventory_ids)
                or (
                    action.action == "network.passive_discovery"
                    and self._network_interfaces
                )
                or (action.action.startswith("camera.") and self._camera_ids)
            )
        )

    @property
    def cameras(self) -> tuple[CameraMenuEntry, ...]:
        return self._cameras

    @property
    def inventories(self) -> tuple[InventoryMenuEntry, ...]:
        return self._inventories

    @property
    def networks(self) -> tuple[NetworkMenuEntry, ...]:
        return self._networks

    def compose(
        self,
        action: str,
        target_id: str,
        *,
        requested_at: datetime,
        command_id: str,
        correlation_id: str,
        duration_seconds: int | None = None,
        changes_only: bool | None = None,
        maximum_candidates: int | None = None,
    ) -> dict[str, object]:
        if requested_at.tzinfo is None:
            raise ValueError("requested_at must be timezone-aware")
        _require_typed_id(command_id)
        _require_typed_id(correlation_id)
        selected = next(
            (candidate for candidate in self._ACTIONS if candidate.action == action),
            None,
        )
        if selected is None:
            raise CommandCompositionRejectedError("ACTION_NOT_REGISTERED")
        registered_targets: Collection[str]
        if action == "asset.list":
            registered_targets = self._inventory_ids
        elif action == "network.passive_discovery":
            registered_targets = self._network_interfaces.keys()
        else:
            registered_targets = self._camera_ids
        if target_id not in registered_targets:
            raise CommandCompositionRejectedError("TARGET_NOT_REGISTERED")

        if action == "camera.status":
            if duration_seconds is not None:
                raise CommandCompositionRejectedError("DURATION_NOT_APPLICABLE")
            if changes_only is not None:
                raise CommandCompositionRejectedError("FILTER_NOT_APPLICABLE")
            if maximum_candidates is not None:
                raise CommandCompositionRejectedError("LIMIT_NOT_APPLICABLE")
            parameters: dict[str, object] = {}
        elif action == "camera.monitor":
            if (
                isinstance(duration_seconds, bool)
                or not isinstance(duration_seconds, int)
                or not 1 <= duration_seconds <= 300
            ):
                raise CommandCompositionRejectedError("DURATION_INVALID")
            if changes_only is not None:
                raise CommandCompositionRejectedError("FILTER_NOT_APPLICABLE")
            if maximum_candidates is not None:
                raise CommandCompositionRejectedError("LIMIT_NOT_APPLICABLE")
            parameters = {"duration_seconds": duration_seconds}
        elif action == "asset.list":
            if duration_seconds is not None:
                raise CommandCompositionRejectedError("DURATION_NOT_APPLICABLE")
            if maximum_candidates is not None:
                raise CommandCompositionRejectedError("LIMIT_NOT_APPLICABLE")
            selected_filter = True if changes_only is None else changes_only
            if not isinstance(selected_filter, bool):
                raise CommandCompositionRejectedError("FILTER_INVALID")
            parameters = {"changes_only": selected_filter}
        else:
            if changes_only is not None:
                raise CommandCompositionRejectedError("FILTER_NOT_APPLICABLE")
            if (
                isinstance(duration_seconds, bool)
                or not isinstance(duration_seconds, int)
                or not 1 <= duration_seconds <= 120
            ):
                raise CommandCompositionRejectedError("DURATION_INVALID")
            selected_limit = 32 if maximum_candidates is None else maximum_candidates
            if (
                isinstance(selected_limit, bool)
                or not isinstance(selected_limit, int)
                or not 1 <= selected_limit <= 128
            ):
                raise CommandCompositionRejectedError("CANDIDATE_LIMIT_INVALID")
            parameters = {
                "duration_seconds": duration_seconds,
                "interface_id": self._network_interfaces[target_id],
                "maximum_candidates": selected_limit,
            }

        return {
            "contract_version": 1,
            "command_id": command_id,
            "actor_id": self._actor_id,
            "organization_id": self._organization_id,
            "source_device_id": self._device_id,
            "profile": selected.profile,
            "action": selected.action,
            "targets": [target_id],
            "parameters": parameters,
            "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
            "correlation_id": correlation_id,
        }


def _require_typed_id(value: str) -> None:
    if len(value) > 160 or _TYPED_IDENTIFIER.fullmatch(value) is None:
        raise ValueError("typed identifier is invalid")

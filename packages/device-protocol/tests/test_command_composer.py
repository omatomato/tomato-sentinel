import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from tomato_sentinel_device_protocol import (
    CameraMenuEntry,
    CardputerSimulator,
    CommandCompositionRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    InventoryMenuEntry,
    NetworkMenuEntry,
    ProvisionedDevice,
    RegisteredCommandComposer,
    load_board_profile,
)
from tomato_sentinel_policy import Profile

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 26, 21, 0, tzinfo=UTC)
SECRET = b"command-composer-simulation-secret"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def composer() -> RegisteredCommandComposer:
    return RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(
            CameraMenuEntry("camera:garage-01", "Garage"),
            CameraMenuEntry("camera:entrance-01", "Entrance"),
        ),
    )


def device_and_verifier() -> tuple[CardputerSimulator, DeviceMessageVerifier]:
    board = load_board_profile(
        load_json(PROFILES / "cardputer.original.v1.json"),
        load_json(SCHEMAS / "board-profile.schema.json"),
    )
    device = CardputerSimulator(
        device_id="cardputer:01",
        key_id="device-key:01",
        secret=SECRET,
        board_profile=board,
        firmware_version="0.2.2-sim",
        boot_id="boot:composer-01",
    )
    registry = DeviceRegistry()
    registry.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board,
            firmware_version="0.2.2-sim",
        ),
        SECRET,
    )
    validator = DeviceProtocolValidator(
        envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
        payload_schemas={
            "text_command": load_json(SCHEMAS / "command.schema.json"),
        },
    )
    return device, DeviceMessageVerifier(validator, registry)


def test_menu_exposes_only_registered_camera_actions() -> None:
    menu = composer()

    assert [(item.action, item.profile, item.risk_class) for item in menu.actions] == [
        ("camera.status", "assistant", "R0"),
        ("camera.monitor", "sentinel", "R1"),
    ]
    assert [camera.camera_id for camera in menu.cameras] == [
        "camera:garage-01",
        "camera:entrance-01",
    ]


def test_inventory_menu_composes_only_stored_read_request() -> None:
    menu = RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(),
        inventories=(InventoryMenuEntry("inventory:primary", "Home lab"),),
    )

    payload = menu.compose(
        "asset.list",
        "inventory:primary",
        requested_at=NOW,
        command_id="command:menu-assets-01",
        correlation_id="correlation:menu-assets-01",
    )

    assert [(item.action, item.profile) for item in menu.actions] == [
        ("asset.list", "inventory"),
    ]
    assert payload["parameters"] == {"changes_only": True}
    assert payload["profile"] == "inventory"


def test_passive_discovery_menu_uses_preconfigured_network_and_interface() -> None:
    menu = RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(),
        networks=(
            NetworkMenuEntry(
                "network:lab",
                "Lab network",
                "interface:edge-lan",
            ),
        ),
    )

    payload = menu.compose(
        "network.passive_discovery",
        "network:lab",
        requested_at=NOW,
        command_id="command:menu-discovery-01",
        correlation_id="correlation:menu-discovery-01",
        duration_seconds=30,
        maximum_candidates=16,
    )

    assert [(item.action, item.risk_class) for item in menu.actions] == [
        ("network.passive_discovery", "R1"),
    ]
    assert payload["profile"] == "inventory"
    assert payload["parameters"] == {
        "duration_seconds": 30,
        "interface_id": "interface:edge-lan",
        "maximum_candidates": 16,
    }


def test_status_selection_builds_and_signs_a_valid_structured_command() -> None:
    payload = composer().compose(
        "camera.status",
        "camera:garage-01",
        requested_at=NOW,
        command_id="command:menu-status-01",
        correlation_id="correlation:menu-status-01",
    )
    Draft202012Validator(
        load_json(SCHEMAS / "command.schema.json"),
        format_checker=FormatChecker(),
    ).validate(payload)
    device, verifier = device_and_verifier()
    envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:menu-status-01",
    )

    verified = verifier.verify(envelope, received_at=NOW)

    assert verified.payload["action"] == "camera.status"
    assert verified.payload["parameters"] == {}


def test_monitor_selection_requires_sentinel_profile_and_bounded_duration() -> None:
    payload = composer().compose(
        "camera.monitor",
        "camera:entrance-01",
        requested_at=NOW,
        command_id="command:menu-monitor-01",
        correlation_id="correlation:menu-monitor-01",
        duration_seconds=120,
    )
    device, verifier = device_and_verifier()

    with pytest.raises(PermissionError, match="visible active profile"):
        device.text_command_message(
            payload,
            sent_at=NOW,
            correlation_id="correlation:menu-monitor-01",
        )
    device.switch_profile(Profile.SENTINEL, changed_at=NOW, unlocked=True)
    envelope = device.text_command_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:menu-monitor-01",
    )

    verified = verifier.verify(envelope, received_at=NOW)

    assert verified.payload["profile"] == "sentinel"
    assert verified.payload["parameters"] == {"duration_seconds": 120}


@pytest.mark.parametrize(
    ("action", "camera_id", "duration", "reason_code"),
    [
        ("camera.delete", "camera:garage-01", None, "ACTION_NOT_REGISTERED"),
        ("camera.status", "camera:unknown", None, "TARGET_NOT_REGISTERED"),
        ("camera.status", "camera:garage-01", 10, "DURATION_NOT_APPLICABLE"),
        ("camera.monitor", "camera:garage-01", None, "DURATION_INVALID"),
        ("camera.monitor", "camera:garage-01", 301, "DURATION_INVALID"),
    ],
)
def test_menu_composition_fails_closed(
    action: str,
    camera_id: str,
    duration: int | None,
    reason_code: str,
) -> None:
    with pytest.raises(CommandCompositionRejectedError) as error:
        composer().compose(
            action,
            camera_id,
            requested_at=NOW,
            command_id="command:menu-denied-01",
            correlation_id="correlation:menu-denied-01",
            duration_seconds=duration,
        )

    assert error.value.reason_code == reason_code


@pytest.mark.parametrize(
    ("target", "duration", "maximum_candidates", "reason_code"),
    [
        ("network:unknown", 30, 16, "TARGET_NOT_REGISTERED"),
        ("network:lab", 0, 16, "DURATION_INVALID"),
        ("network:lab", 121, 16, "DURATION_INVALID"),
        ("network:lab", 30, 0, "CANDIDATE_LIMIT_INVALID"),
        ("network:lab", 30, 129, "CANDIDATE_LIMIT_INVALID"),
    ],
)
def test_passive_discovery_menu_limits_fail_closed(
    target: str,
    duration: int,
    maximum_candidates: int,
    reason_code: str,
) -> None:
    menu = RegisteredCommandComposer(
        actor_id="user:01",
        organization_id="org:01",
        device_id="cardputer:01",
        cameras=(),
        networks=(
            NetworkMenuEntry(
                "network:lab",
                "Lab network",
                "interface:edge-lan",
            ),
        ),
    )

    with pytest.raises(CommandCompositionRejectedError) as error:
        menu.compose(
            "network.passive_discovery",
            target,
            requested_at=NOW,
            command_id="command:menu-discovery-denied",
            correlation_id="correlation:menu-discovery-denied",
            duration_seconds=duration,
            maximum_candidates=maximum_candidates,
        )

    assert error.value.reason_code == reason_code

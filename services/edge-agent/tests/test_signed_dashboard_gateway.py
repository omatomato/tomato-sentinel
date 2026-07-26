import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tomato_sentinel_device_protocol import (
    CardputerSimulator,
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    ProvisionedDevice,
    load_board_profile,
)
from tomato_sentinel_edge_agent import (
    BoundLabOperator,
    DeviceLabConfirmationGateway,
    DeviceLabDashboardGateway,
    DeviceLabDashboardRejectedError,
    LabDashboardPresenter,
    LocalEdgeApplication,
)
from tomato_sentinel_experiments import (
    ExperimentProposalValidator,
    FixtureLocalExperimentModel,
    ModuleRegistry,
)
from tomato_sentinel_policy import Profile

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
MODULES = ROOT / "config" / "modules"
PROFILES = ROOT / "firmware" / "cardputer" / "board_profiles"
NOW = datetime(2026, 7, 26, 16, 0, tzinfo=UTC)
SECRET = b"edge-dashboard-simulation-secret-0001"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def build_gateway() -> tuple[
    CardputerSimulator,
    DeviceLabDashboardGateway,
    DeviceLabConfirmationGateway,
]:
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
        boot_id="boot:edge-dashboard-01",
    )
    device.switch_profile(
        Profile.LAB,
        changed_at=NOW,
        unlocked=True,
        operator_id="user:researcher-01",
        active_scope_id="scope:lab-01",
        expires_at=NOW + timedelta(minutes=10),
    )
    devices = DeviceRegistry()
    devices.provision(
        ProvisionedDevice(
            device_id="cardputer:01",
            key_id="device-key:01",
            board_profile=board,
            firmware_version="0.2.2-sim",
        ),
        SECRET,
    )
    verifier = DeviceMessageVerifier(
        DeviceProtocolValidator(
            envelope_schema=load_json(SCHEMAS / "device-message.schema.json"),
            payload_schemas={
                "lab_dashboard_request": load_json(
                    SCHEMAS / "lab-dashboard-request.schema.json"
                ),
                "lab_plan_confirmation": load_json(
                    SCHEMAS / "lab-plan-confirmation.schema.json"
                ),
            },
        ),
        devices,
    )
    modules = ModuleRegistry(load_json(SCHEMAS / "module-manifest.schema.json"))
    modules.register(load_json(MODULES / "lab.spectra.v2.json"))
    modules.register(load_json(MODULES / "lab.soc.v1.json"))
    application = LocalEdgeApplication(
        edge_id="edge:local-01",
        organization_id="organization:01",
        agent_version="0.1.0-sim",
        modules=modules,
        proposal_model=FixtureLocalExperimentModel(
            {
                "prompt:spectra": {
                    "contract_version": 1,
                    "module_alias": "spectra",
                    "target_alias": "controlled_fixture",
                    "fixture_aliases": ["baseline"],
                    "parameters": {
                        "channel": "optical_fixture",
                        "encoding": "manchester",
                        "error_correction": "hamming84",
                        "duration_seconds": 30,
                        "sample_count": 120,
                        "noise_percent": 10,
                    },
                    "execution_mode": "simulation",
                }
            }
        ),
        proposal_validator=ExperimentProposalValidator(
            load_json(SCHEMAS / "experiment-proposal.schema.json")
        ),
    )
    presenter = LabDashboardPresenter(
        load_json(SCHEMAS / "lab-dashboard-view.schema.json"),
        modules,
    )
    return (
        device,
        DeviceLabDashboardGateway(verifier, application, presenter),
        DeviceLabConfirmationGateway(
            verifier,
            {
                "cardputer:01": BoundLabOperator(
                    actor_id="user:researcher-01",
                    organization_id="organization:01",
                )
            },
        ),
    )


def request(
    *,
    action: str,
    parameters: dict[str, object],
    requested_at: datetime = NOW,
) -> dict[str, object]:
    suffix = "capabilities" if action.endswith("capabilities") else "proposal"
    return {
        "contract_version": 1,
        "request_id": f"edge-request:dashboard-{suffix}",
        "organization_id": "organization:01",
        "source_device_id": "cardputer:01",
        "active_profile": "lab",
        "scope_id": "scope:lab-01",
        "action": action,
        "parameters": parameters,
        "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
        "correlation_id": f"correlation:dashboard-{suffix}",
    }


def test_signed_dashboard_request_returns_edge_capabilities() -> None:
    device, gateway, _ = build_gateway()
    payload = request(action="lab.dashboard.capabilities", parameters={})
    envelope = device.lab_dashboard_request_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:dashboard-capabilities",
    )

    result = gateway.handle(envelope, received_at=NOW)

    assert result["execution_mode"] == "simulation"
    assert result["edge_id"] == "edge:local-01"
    assert result["view_type"] == "lab.modules"
    assert len(result["tiles"]) == 2


def test_signed_dashboard_request_can_only_obtain_reviewed_proposal() -> None:
    device, gateway, _ = build_gateway()
    payload = request(
        action="lab.experiment.proposal",
        parameters={"prompt_id": "prompt:spectra"},
    )
    envelope = device.lab_dashboard_request_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:dashboard-proposal",
    )

    result = gateway.handle(envelope, received_at=NOW)

    assert result["module_alias"] == "spectra"
    assert result["execution_mode"] == "simulation"


def test_gateway_rejects_timestamp_mismatch_after_signature_verification() -> None:
    device, gateway, _ = build_gateway()
    payload = request(
        action="lab.dashboard.capabilities",
        parameters={},
        requested_at=NOW + timedelta(seconds=1),
    )
    envelope = device.lab_dashboard_request_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:dashboard-capabilities",
    )

    with pytest.raises(DeviceLabDashboardRejectedError) as rejected:
        gateway.handle(envelope, received_at=NOW)

    assert rejected.value.reason_code == "REQUEST_TIMESTAMP_MISMATCH"


def test_unregistered_dashboard_payload_shape_is_rejected_before_gateway() -> None:
    device, gateway, _ = build_gateway()
    payload = request(
        action="lab.dashboard.capabilities",
        parameters={"prompt_id": "prompt:spectra"},
    )
    envelope = device.lab_dashboard_request_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:dashboard-capabilities",
    )

    with pytest.raises(DeviceMessageRejectedError) as rejected:
        gateway.handle(envelope, received_at=NOW)

    assert rejected.value.reason_code == "PAYLOAD_SCHEMA_INVALID"


def test_signed_physical_confirmation_becomes_short_lived_policy_input() -> None:
    device, _, confirmations = build_gateway()
    payload = {
        "contract_version": 1,
        "confirmation_id": "confirmation:lab-01",
        "actor_id": "user:researcher-01",
        "organization_id": "organization:01",
        "source_device_id": "cardputer:01",
        "active_profile": "lab",
        "scope_id": "scope:lab-01",
        "plan_hash": "sha256:" + "b" * 64,
        "input_source": "physical_confirm_key",
        "confirmed_at": NOW.isoformat().replace("+00:00", "Z"),
        "correlation_id": "correlation:confirmation-01",
    }
    envelope = device.lab_plan_confirmation_message(
        payload,
        sent_at=NOW,
        correlation_id="correlation:confirmation-01",
    )

    confirmation = confirmations.handle(envelope, received_at=NOW)

    assert confirmation.plan_hash == payload["plan_hash"]
    assert confirmation.method.value == "physical"
    assert confirmation.valid_until == NOW + timedelta(seconds=60)

"""Closed local CLI for inspecting simulated edge-lab state on the PC."""

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tomato_sentinel_edge_agent import (
    AuthenticatedLocalPeer,
    LabDashboardPresenter,
    LocalEdgeApplication,
)
from tomato_sentinel_experiments import (
    ExperimentProposalValidator,
    FixtureLocalExperimentModel,
    InactiveHardwareRegistry,
    ModuleRegistry,
)

ROOT = Path(__file__).parents[4]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
MODULES = ROOT / "config" / "modules"
HARDWARE = ROOT / "config" / "hardware-modules"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tomato-edge-lab",
        description="Read-only local diagnostics for the simulated Tomato lab edge.",
    )
    parser.add_argument(
        "command",
        choices=("capabilities", "dashboard", "proposal", "validate-config"),
    )
    parser.add_argument("--prompt", choices=("spectra", "soc"))
    parsed = parser.parse_args(arguments)

    modules = _load_modules()
    output: Mapping[str, object]
    if parsed.command == "validate-config":
        output = {
            "contract_version": 1,
            "execution_mode": "simulation",
            "module_count": len(modules.modules),
            "inactive_hardware_count": _load_hardware_count(),
            "network_listener": "disabled",
        }
    else:
        application = _application(modules)
        now = datetime.now(UTC)
        peer = AuthenticatedLocalPeer(
            device_id="device:edge-lab-console",
            organization_id="organization:01",
            authenticated=True,
        )
        if parsed.command == "capabilities":
            output = application.handle(
                _request("edge.capabilities", "edge-request:console-capabilities", {}),
                peer=peer,
                received_at=now,
            )
        elif parsed.command == "dashboard":
            report = application.handle(
                _request("edge.capabilities", "edge-request:console-dashboard", {}),
                peer=peer,
                received_at=now,
            )
            output = LabDashboardPresenter(
                _load_json(SCHEMAS / "lab-dashboard-view.schema.json"),
                modules,
            ).capabilities_view(report)
        else:
            if parsed.prompt is None:
                parser.error("proposal requires --prompt spectra or --prompt soc")
            output = application.handle(
                _request(
                    "experiment.propose",
                    f"edge-request:console-proposal-{parsed.prompt}",
                    {"prompt_id": f"prompt:{parsed.prompt}"},
                ),
                peer=peer,
                received_at=now,
            )
    print(json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


def _application(modules: ModuleRegistry) -> LocalEdgeApplication:
    return LocalEdgeApplication(
        edge_id="edge:local-console",
        organization_id="organization:01",
        agent_version="0.1.0-sim",
        modules=modules,
        proposal_model=FixtureLocalExperimentModel(
            {"prompt:spectra": _proposal("spectra"), "prompt:soc": _proposal("soc")}
        ),
        proposal_validator=ExperimentProposalValidator(
            _load_json(SCHEMAS / "experiment-proposal.schema.json")
        ),
    )


def _proposal(module_alias: str) -> Mapping[str, object]:
    parameters: Mapping[str, object]
    if module_alias == "spectra":
        parameters = {
            "encoding": "manchester",
            "duration_seconds": 30,
            "sample_count": 120,
            "noise_percent": 10,
        }
    else:
        parameters = {
            "scenario": "correlation_integrity",
            "duration_seconds": 30,
            "sample_count": 120,
            "detection_sensitivity": 80,
        }
    return {
        "contract_version": 1,
        "module_alias": module_alias,
        "target_alias": "controlled_fixture",
        "fixture_aliases": ["baseline"],
        "parameters": parameters,
        "execution_mode": "simulation",
    }


def _request(
    method: str,
    request_id: str,
    body: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "contract_version": 1,
        "request_id": request_id,
        "method": method,
        "body": dict(body),
    }


def _load_modules() -> ModuleRegistry:
    modules = ModuleRegistry(_load_json(SCHEMAS / "module-manifest.schema.json"))
    for path in sorted(MODULES.glob("*.json")):
        modules.register(_load_json(path))
    return modules


def _load_hardware_count() -> int:
    hardware = InactiveHardwareRegistry(
        _load_json(SCHEMAS / "hardware-module-profile.schema.json")
    )
    for path in sorted(HARDWARE.glob("*.json")):
        hardware.register(_load_json(path))
    return len(hardware.profiles)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return cast(dict[str, Any], json.load(source))


if __name__ == "__main__":
    raise SystemExit(main())

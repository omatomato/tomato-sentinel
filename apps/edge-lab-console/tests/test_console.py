import json

import pytest
from tomato_sentinel_edge_console.__main__ import main


def test_validate_config_reports_only_inactive_hardware(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate-config"]) == 0

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "contract_version": 1,
        "execution_mode": "simulation",
        "inactive_hardware_count": 4,
        "module_count": 3,
        "network_listener": "disabled",
    }


def test_dashboard_lists_bounded_simulation_tiles(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["dashboard"]) == 0

    output = json.loads(capsys.readouterr().out)

    assert output["view_type"] == "lab.modules"
    assert output["execution_mode"] == "simulation"
    assert [tile["module_id"] for tile in output["tiles"]] == [
        "lab.soc",
        "lab.spectra",
        "lab.spectra",
    ]
    assert [tile["module_version"] for tile in output["tiles"]] == [1, 1, 2]


def test_proposal_requires_closed_prompt_selection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["proposal", "--prompt", "spectra"]) == 0

    output = json.loads(capsys.readouterr().out)

    assert output["module_alias"] == "spectra"
    assert output["execution_mode"] == "simulation"
    assert output["parameters"]["error_correction"] == "hamming84"

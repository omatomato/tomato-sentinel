from typing import cast

import pytest
from tomato_sentinel_experiments import simulate_spectra_channel


@pytest.mark.parametrize("encoding", ["ask", "fsk", "manchester", "pwm"])
def test_zero_noise_round_trip_preserves_fixture_payload(encoding: str) -> None:
    result = simulate_spectra_channel(
        channel="optical_fixture",
        encoding=encoding,
        error_correction="none",
        sample_count=257,
        noise_percent=0,
        seed="fixture:zero-noise",
    )

    assert result.injected_sample_errors == 0
    assert result.channel_bit_errors == 0
    assert result.bit_errors == 0
    assert result.ber == 0
    assert result.frame_sync_ok
    assert result.checksum_ok


def test_hamming84_corrects_single_injected_sample_error() -> None:
    result = simulate_spectra_channel(
        channel="optical_fixture",
        encoding="ask",
        error_correction="hamming84",
        sample_count=8,
        noise_percent=1,
        seed="fixture:single-error",
    )

    assert result.injected_sample_errors == 1
    assert result.channel_bit_errors == 1
    assert result.corrected_errors == 1
    assert result.uncorrectable_blocks == 0
    assert result.bit_errors == 0
    assert result.frame_sync_ok
    assert result.checksum_ok


def test_noisy_channel_is_reproducible_for_exact_plan_seed() -> None:
    first = simulate_spectra_channel(
        channel="acoustic_fixture",
        encoding="fsk",
        error_correction="hamming84",
        sample_count=512,
        noise_percent=9,
        seed="sha256:exact-plan|fixture:baseline-01",
    )
    second = simulate_spectra_channel(
        channel="acoustic_fixture",
        encoding="fsk",
        error_correction="hamming84",
        sample_count=512,
        noise_percent=9,
        seed="sha256:exact-plan|fixture:baseline-01",
    )

    assert first == second
    assert first.injected_sample_errors > 0
    assert 0 <= first.channel_ber <= 1
    assert 0 <= first.ber <= 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("channel", "microphone"),
        ("encoding", "raw"),
        ("error_correction", "reed_solomon"),
        ("sample_count", 7),
        ("sample_count", 65_537),
        ("noise_percent", -1),
        ("noise_percent", 51),
        ("seed", ""),
    ],
)
def test_simulator_denies_unregistered_or_unbounded_input(
    field: str,
    value: object,
) -> None:
    parameters: dict[str, object] = {
        "channel": "optical_fixture",
        "encoding": "manchester",
        "error_correction": "none",
        "sample_count": 64,
        "noise_percent": 5,
        "seed": "fixture:bounded",
    }
    parameters[field] = value

    with pytest.raises(ValueError):
        simulate_spectra_channel(
            channel=str(parameters["channel"]),
            encoding=str(parameters["encoding"]),
            error_correction=str(parameters["error_correction"]),
            sample_count=cast(int, parameters["sample_count"]),
            noise_percent=cast(int, parameters["noise_percent"]),
            seed=str(parameters["seed"]),
        )

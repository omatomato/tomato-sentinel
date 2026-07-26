"""Deterministic fixture-only executors for safe lab integration."""

from dataclasses import dataclass

from .engine import ExperimentSession, ExperimentStep
from .models import ExperimentPlan
from .spectra import simulate_spectra_channel


@dataclass(slots=True)
class _SpectraSession:
    plan: ExperimentPlan
    _step: int = 0
    _cancelled: bool = False

    def advance(self) -> ExperimentStep:
        if self._cancelled:
            raise RuntimeError("session cancelled")
        self._step += 1
        sample_count = _required_int(self.plan, "sample_count")
        noise_percent = _required_int(self.plan, "noise_percent")
        bit_errors = min(sample_count, sample_count * noise_percent // 200)
        if self._step < 3:
            return ExperimentStep(
                complete=False,
                progress_percent=self._step * 33,
                metrics={
                    "samples_processed": sample_count * self._step // 3,
                    "execution_mode": "simulation",
                },
            )
        return ExperimentStep(
            complete=True,
            progress_percent=100,
            metrics={
                "samples_processed": sample_count,
                "execution_mode": "simulation",
            },
            result={
                "execution_mode": "simulation",
                "encoding": self.plan.parameters["encoding"],
                "sample_count": sample_count,
                "bit_errors": bit_errors,
                "ber": bit_errors / sample_count,
                "checksum_ok": bit_errors == 0,
            },
        )

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True, slots=True)
class SpectraFixtureExecutor:
    @property
    def executor_id(self) -> str:
        return "executor:spectra-fixture-v1"

    def create_session(self, plan: ExperimentPlan) -> ExperimentSession:
        return _SpectraSession(plan)


@dataclass(slots=True)
class _SpectraSimulationSession:
    plan: ExperimentPlan
    _step: int = 0
    _cancelled: bool = False

    def advance(self) -> ExperimentStep:
        if self._cancelled:
            raise RuntimeError("session cancelled")
        self._step += 1
        sample_count = _required_int(self.plan, "sample_count")
        if self._step < 3:
            return ExperimentStep(
                complete=False,
                progress_percent=self._step * 33,
                metrics={
                    "samples_processed": sample_count * self._step // 3,
                    "execution_mode": "simulation",
                },
            )
        result = simulate_spectra_channel(
            channel=_required_str(self.plan, "channel"),
            encoding=_required_str(self.plan, "encoding"),
            error_correction=_required_str(self.plan, "error_correction"),
            sample_count=sample_count,
            noise_percent=_required_int(self.plan, "noise_percent"),
            seed="|".join((self.plan.plan_hash, *self.plan.fixture_ids)),
        )
        return ExperimentStep(
            complete=True,
            progress_percent=100,
            metrics={
                "samples_processed": sample_count,
                "transmitted_samples": result.transmitted_sample_count,
                "execution_mode": "simulation",
            },
            result=result.as_mapping(),
        )

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True, slots=True)
class SpectraSimulationExecutor:
    @property
    def executor_id(self) -> str:
        return "executor:spectra-simulator-v2"

    def create_session(self, plan: ExperimentPlan) -> ExperimentSession:
        return _SpectraSimulationSession(plan)


@dataclass(slots=True)
class _SocSession:
    plan: ExperimentPlan
    _step: int = 0
    _cancelled: bool = False

    def advance(self) -> ExperimentStep:
        if self._cancelled:
            raise RuntimeError("session cancelled")
        self._step += 1
        generated = _required_int(self.plan, "sample_count")
        sensitivity = _required_int(self.plan, "detection_sensitivity")
        detected = min(generated, generated * sensitivity // 100)
        if self._step < 3:
            return ExperimentStep(
                complete=False,
                progress_percent=self._step * 33,
                metrics={
                    "events_processed": generated * self._step // 3,
                    "execution_mode": "simulation",
                },
            )
        return ExperimentStep(
            complete=True,
            progress_percent=100,
            metrics={
                "events_processed": generated,
                "execution_mode": "simulation",
            },
            result={
                "execution_mode": "simulation",
                "scenario": self.plan.parameters["scenario"],
                "generated_events": generated,
                "detected_events": detected,
                "missed_events": generated - detected,
                "mean_latency_ms": max(1, 201 - sensitivity * 2),
            },
        )

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True, slots=True)
class SocFixtureExecutor:
    @property
    def executor_id(self) -> str:
        return "executor:soc-fixture-v1"

    def create_session(self, plan: ExperimentPlan) -> ExperimentSession:
        return _SocSession(plan)


def _required_int(plan: ExperimentPlan, key: str) -> int:
    value = plan.parameters[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_str(plan: ExperimentPlan, key: str) -> str:
    value = plan.parameters[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value

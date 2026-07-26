"""Public API for the modular Tomato Sentinel experiment engine."""

from .capabilities import (
    AvailableModule,
    CapabilityReportRejectedError,
    CapabilityReportValidator,
    ValidatedCapabilityReport,
    canonical_capability_report_hash,
)
from .engine import (
    ExperimentAuditRecord,
    ExperimentAuthorizationContext,
    ExperimentEngine,
    ExperimentEngineRejectedError,
    ExperimentExecutor,
    ExperimentJob,
    ExperimentSession,
    ExperimentState,
    ExperimentStep,
    InMemoryExperimentAuditSink,
    build_policy_registry,
)
from .fake_executors import (
    SocFixtureExecutor,
    SpectraFixtureExecutor,
    SpectraSimulationExecutor,
)
from .hardware_profiles import (
    HardwareProfileRejectedError,
    InactiveHardwareProfile,
    InactiveHardwareRegistry,
)
from .models import ExecutionLocation, ExperimentPlan, ModuleManifest
from .plans import (
    ExperimentPlanRejectedError,
    ExperimentPlanValidator,
    canonical_plan_hash,
)
from .proposals import (
    ExperimentProposalBinder,
    ExperimentProposalRejectedError,
    ExperimentProposalValidator,
    FixtureLocalExperimentModel,
    LocalExperimentModel,
)
from .registry import ModuleRegistry, ModuleRejectedError
from .spectra import SpectraSimulationResult, simulate_spectra_channel

__all__ = [
    "AvailableModule",
    "CapabilityReportRejectedError",
    "CapabilityReportValidator",
    "ExecutionLocation",
    "ExperimentAuditRecord",
    "ExperimentAuthorizationContext",
    "ExperimentEngine",
    "ExperimentEngineRejectedError",
    "ExperimentExecutor",
    "ExperimentJob",
    "ExperimentPlan",
    "ExperimentPlanRejectedError",
    "ExperimentPlanValidator",
    "ExperimentProposalBinder",
    "ExperimentProposalRejectedError",
    "ExperimentProposalValidator",
    "ExperimentSession",
    "ExperimentState",
    "ExperimentStep",
    "FixtureLocalExperimentModel",
    "HardwareProfileRejectedError",
    "InMemoryExperimentAuditSink",
    "InactiveHardwareProfile",
    "InactiveHardwareRegistry",
    "LocalExperimentModel",
    "ModuleManifest",
    "ModuleRegistry",
    "ModuleRejectedError",
    "SocFixtureExecutor",
    "SpectraFixtureExecutor",
    "SpectraSimulationExecutor",
    "SpectraSimulationResult",
    "ValidatedCapabilityReport",
    "build_policy_registry",
    "canonical_capability_report_hash",
    "canonical_plan_hash",
    "simulate_spectra_channel",
]

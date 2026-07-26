import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tomato_sentinel_device_protocol import (
    CardputerLabDashboard,
    LabDashboardState,
)
from tomato_sentinel_edge_agent import (
    AuthenticatedLocalPeer,
    LocalEdgeApplication,
    LocalEdgeBoundaryRejectedError,
)
from tomato_sentinel_experiments import (
    CapabilityReportValidator,
    ExperimentAuthorizationContext,
    ExperimentEngine,
    ExperimentEngineRejectedError,
    ExperimentPlanRejectedError,
    ExperimentPlanValidator,
    ExperimentProposalBinder,
    ExperimentProposalValidator,
    ExperimentState,
    FixtureLocalExperimentModel,
    HardwareProfileRejectedError,
    InactiveHardwareRegistry,
    InMemoryExperimentAuditSink,
    ModuleRegistry,
    SocFixtureExecutor,
    SpectraFixtureExecutor,
)
from tomato_sentinel_policy import (
    ActorContext,
    Confirmation,
    ConfirmationMethod,
    DeviceContext,
    OperationScope,
    Profile,
    TrustState,
)

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "packages" / "contracts" / "schemas" / "v1"
MODULES = ROOT / "config" / "modules"
HARDWARE = ROOT / "config" / "hardware-modules"
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value: dict[str, Any] = json.load(source)
    return value


def module_registry() -> ModuleRegistry:
    registry = ModuleRegistry(load_json(SCHEMAS / "module-manifest.schema.json"))
    registry.register(load_json(MODULES / "lab.spectra.v1.json"))
    registry.register(load_json(MODULES / "lab.soc.v1.json"))
    return registry


def proposal_for(module_alias: str) -> dict[str, object]:
    if module_alias == "spectra":
        parameters: dict[str, object] = {
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


def build_flow(
    module_alias: str,
) -> tuple[
    ExperimentEngine,
    dict[str, object],
    ExperimentAuthorizationContext,
    InMemoryExperimentAuditSink,
    LocalEdgeApplication,
]:
    modules = module_registry()
    proposal_validator = ExperimentProposalValidator(
        load_json(SCHEMAS / "experiment-proposal.schema.json")
    )
    model = FixtureLocalExperimentModel(
        {f"prompt:{module_alias}": proposal_for(module_alias)}
    )
    edge = LocalEdgeApplication(
        edge_id="edge:local-01",
        organization_id="organization:01",
        agent_version="0.1.0-sim",
        modules=modules,
        proposal_model=model,
        proposal_validator=proposal_validator,
    )
    peer = AuthenticatedLocalPeer(
        device_id="device:cardputer-01",
        organization_id="organization:01",
        authenticated=True,
    )
    capability_payload = edge.handle(
        {
            "contract_version": 1,
            "request_id": f"edge-request:capabilities-{module_alias}",
            "method": "edge.capabilities",
            "body": {},
        },
        peer=peer,
        received_at=NOW,
    )
    capability_report = CapabilityReportValidator(
        load_json(SCHEMAS / "edge-capability-report.schema.json"),
        modules,
    ).validate(
        capability_payload,
        authenticated_edge_id="edge:local-01",
        authenticated_organization_id="organization:01",
        evaluated_at=NOW,
    )
    proposal = edge.handle(
        {
            "contract_version": 1,
            "request_id": f"edge-request:proposal-{module_alias}",
            "method": "experiment.propose",
            "body": {"prompt_id": f"prompt:{module_alias}"},
        },
        peer=peer,
        received_at=NOW,
    )
    plan_validator = ExperimentPlanValidator(
        load_json(SCHEMAS / "experiment-plan.schema.json"),
        modules,
    )
    actor = ActorContext(
        actor_id="user:researcher-01",
        organization_id="organization:01",
        roles=frozenset({"researcher"}),
    )
    device = DeviceContext(
        device_id="device:cardputer-01",
        organization_id="organization:01",
        trust_state=TrustState.TRUSTED,
    )
    payload, plan = ExperimentProposalBinder(
        validator=proposal_validator,
        plan_validator=plan_validator,
        module_aliases={"spectra": ("lab.spectra", 1), "soc": ("lab.soc", 1)},
        target_aliases={"controlled_fixture": "lab_target:fixture-01"},
        fixture_aliases={"baseline": "fixture:baseline-01"},
    ).bind(
        proposal,
        experiment_id=f"experiment:{module_alias}-01",
        correlation_id=f"correlation:{module_alias}-01",
        actor=actor,
        source_device=device,
        profile=Profile.LAB,
        operation_scope_id="scope:lab-01",
        requested_at=NOW,
    )
    scope = OperationScope(
        scope_id="scope:lab-01",
        organization_id="organization:01",
        tool_ids=frozenset({"lab.spectra", "lab.soc"}),
        target_ids=frozenset({"lab_target:fixture-01"}),
        valid_until=NOW + timedelta(minutes=2),
    )
    context = ExperimentAuthorizationContext(
        actor=actor,
        device=device,
        operation_scope=scope,
        capability_report=capability_report,
        confirmation=Confirmation(
            actor_id=actor.actor_id,
            device_id=device.device_id,
            plan_hash=plan.plan_hash,
            method=ConfirmationMethod.PHYSICAL,
            valid_until=NOW + timedelta(seconds=60),
        ),
    )
    audit = InMemoryExperimentAuditSink()
    engine = ExperimentEngine(
        plan_validator=plan_validator,
        module_registry=modules,
        executors=(SpectraFixtureExecutor(), SocFixtureExecutor()),
        audit_sink=audit,
    )
    return engine, payload, context, audit, edge


@pytest.mark.parametrize("module_alias", ["spectra", "soc"])
def test_registered_fixture_modules_complete_as_simulation(module_alias: str) -> None:
    engine, payload, context, audit, _ = build_flow(module_alias)

    job = engine.start(payload, context, evaluated_at=NOW)
    assert job.state is ExperimentState.RUNNING
    for second in range(1, 4):
        job = engine.advance(
            job.plan.experiment_id,
            context,
            advanced_at=NOW + timedelta(seconds=second),
        )

    assert job.state is ExperimentState.COMPLETED
    assert job.result is not None
    assert job.result["execution_mode"] == "simulation"
    assert [record.state for record in audit.records] == [
        ExperimentState.VALIDATED,
        ExperimentState.AUTHORIZED,
        ExperimentState.RUNNING,
        ExperimentState.COMPLETED,
    ]
    assert all(record.executor_edge_id == "edge:local-01" for record in audit.records)


def test_tampered_bound_plan_is_rejected_before_policy() -> None:
    engine, payload, context, audit, _ = build_flow("spectra")
    payload["parameters"] = {
        "encoding": "fsk",
        "duration_seconds": 30,
        "sample_count": 120,
        "noise_percent": 10,
    }

    with pytest.raises(ExperimentPlanRejectedError) as rejected:
        engine.start(payload, context, evaluated_at=NOW)

    assert rejected.value.reason_code == "PLAN_HASH_MISMATCH"
    assert audit.records == []


def test_edge_module_cannot_start_without_capability_report() -> None:
    engine, payload, context, audit, _ = build_flow("spectra")

    with pytest.raises(ExperimentEngineRejectedError) as rejected:
        engine.start(
            payload,
            replace(context, capability_report=None),
            evaluated_at=NOW,
        )

    assert rejected.value.reason_code == "EDGE_CAPABILITY_REPORT_REQUIRED"
    assert audit.records == []


def test_module_cannot_start_without_exact_physical_confirmation() -> None:
    engine, payload, context, audit, _ = build_flow("spectra")

    denied = engine.start(
        payload,
        replace(context, confirmation=None),
        evaluated_at=NOW,
    )

    assert denied.state is ExperimentState.DENIED
    assert denied.reason_code == "AUTHORIZED_CONFIRMATION_REQUIRED"
    assert audit.records[-1].state is ExperimentState.DENIED


def test_running_experiment_can_be_cancelled_idempotently() -> None:
    engine, payload, context, audit, _ = build_flow("soc")
    job = engine.start(payload, context, evaluated_at=NOW)

    cancelled = engine.cancel(
        job.plan.experiment_id,
        context,
        cancelled_at=NOW + timedelta(seconds=1),
    )
    repeated = engine.cancel(
        job.plan.experiment_id,
        context,
        cancelled_at=NOW + timedelta(seconds=2),
    )

    assert cancelled.state is ExperimentState.CANCELLED
    assert repeated.state is ExperimentState.CANCELLED
    assert audit.records[-1].reason_code == "OPERATOR_CANCELLED"


def test_edge_boundary_denies_unauthenticated_peer() -> None:
    _, _, _, _, edge = build_flow("spectra")

    with pytest.raises(LocalEdgeBoundaryRejectedError) as rejected:
        edge.handle(
            {
                "contract_version": 1,
                "request_id": "edge-request:unauthenticated",
                "method": "edge.health",
                "body": {},
            },
            peer=AuthenticatedLocalPeer(
                device_id="device:unknown",
                organization_id="organization:01",
                authenticated=False,
            ),
            received_at=NOW,
        )

    assert rejected.value.reason_code == "EDGE_PEER_UNAUTHENTICATED"


def test_dashboard_accepts_only_advertised_simulated_module() -> None:
    dashboard = CardputerLabDashboard()
    dashboard.apply_capabilities(
        (
            {
                "module_id": "lab.spectra",
                "module_version": 1,
                "display_name": "Spectra Lab",
                "risk_class": "R1",
                "execution_mode": "simulation",
            },
        ),
        active_profile=Profile.LAB,
        active_scope_id="scope:lab-01",
    )
    dashboard.review("lab.spectra", 1)
    review = dashboard.apply_plan_review(
        {
            "experiment_id": "experiment:spectra-01",
            "module_id": "lab.spectra",
            "module_version": 1,
            "targets": ["lab_target:fixture-01"],
            "fixture_ids": ["fixture:baseline-01"],
            "parameters": {"duration_seconds": 30, "sample_count": 120},
            "plan_hash": "sha256:" + "a" * 64,
            "execution_mode": "simulation",
        }
    )
    dashboard.physical_confirmation_received(review.plan_hash)
    dashboard.started("experiment:spectra-01")
    dashboard.update_progress(
        "experiment:spectra-01",
        progress_percent=66,
        metric_label="samples_processed",
        metric_value=80,
    )
    dashboard.completed("experiment:spectra-01")

    assert dashboard.state is LabDashboardState.RESULT
    assert dashboard.progress_percent == 100


def test_physical_profiles_register_only_while_fully_inactive() -> None:
    registry = InactiveHardwareRegistry(
        load_json(SCHEMAS / "hardware-module-profile.schema.json")
    )
    for path in sorted(HARDWARE.glob("*.json")):
        registry.register(load_json(path))
    unsafe = load_json(HARDWARE / "nrf24l01.receive-only.v1.json")
    unsafe["activation_state"] = "enabled"

    with pytest.raises(HardwareProfileRejectedError) as rejected:
        InactiveHardwareRegistry(
            load_json(SCHEMAS / "hardware-module-profile.schema.json")
        ).register(unsafe)

    assert len(registry.profiles) == 4
    assert rejected.value.reason_code == "HARDWARE_PROFILE_INVALID"

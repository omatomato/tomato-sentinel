"""Bounded Cardputer lab dashboard state, independent of physical rendering."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from tomato_sentinel_policy import Profile

MAXIMUM_LAB_MODULE_TILES = 12


class LabDashboardRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class LabDashboardState(StrEnum):
    DISCONNECTED = "disconnected"
    READY = "ready"
    REVIEW = "review"
    RUNNING = "running"
    RESULT = "result"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LabModuleTile:
    module_id: str
    module_version: int
    display_name: str
    risk_class: str
    execution_mode: str


@dataclass(frozen=True, slots=True)
class LabPlanReview:
    experiment_id: str
    module_id: str
    module_version: int
    target_count: int
    fixture_count: int
    duration_seconds: int
    sample_count: int
    plan_hash: str


@dataclass(slots=True)
class CardputerLabDashboard:
    state: LabDashboardState = LabDashboardState.DISCONNECTED
    modules: tuple[LabModuleTile, ...] = ()
    selected_module: LabModuleTile | None = None
    plan_review: LabPlanReview | None = None
    physical_confirmation_hash: str | None = None
    active_experiment_id: str | None = None
    progress_percent: int = 0
    primary_metric_label: str | None = None
    primary_metric_value: int | float | str | None = None
    status_code: str = "EDGE_DISCONNECTED"

    def apply_capabilities(
        self,
        entries: Sequence[Mapping[str, object]],
        *,
        active_profile: Profile,
        active_scope_id: str | None,
    ) -> None:
        if active_profile is not Profile.LAB or active_scope_id is None:
            raise LabDashboardRejectedError("LAB_PROFILE_AND_SCOPE_REQUIRED")
        if len(entries) > MAXIMUM_LAB_MODULE_TILES:
            raise LabDashboardRejectedError("LAB_MODULE_LIMIT_EXCEEDED")
        tiles: list[LabModuleTile] = []
        seen: set[tuple[str, int]] = set()
        for entry in entries:
            required = {
                "module_id",
                "module_version",
                "display_name",
                "risk_class",
                "execution_mode",
            }
            if set(entry) != required:
                raise LabDashboardRejectedError("LAB_MODULE_ENTRY_INVALID")
            module_id = entry["module_id"]
            version = entry["module_version"]
            if (
                not isinstance(module_id, str)
                or not module_id.startswith("lab.")
                or isinstance(version, bool)
                or not isinstance(version, int)
                or version < 1
                or entry["risk_class"] not in {"R0", "R1", "R2"}
                or entry["execution_mode"] != "simulation"
            ):
                raise LabDashboardRejectedError("LAB_MODULE_ENTRY_INVALID")
            key = (module_id, version)
            if key in seen:
                raise LabDashboardRejectedError("LAB_MODULE_DUPLICATED")
            seen.add(key)
            display_name = entry["display_name"]
            if not isinstance(display_name, str) or not 1 <= len(display_name) <= 40:
                raise LabDashboardRejectedError("LAB_MODULE_ENTRY_INVALID")
            tiles.append(
                LabModuleTile(
                    module_id=module_id,
                    module_version=version,
                    display_name=display_name,
                    risk_class=entry["risk_class"],
                    execution_mode="simulation",
                )
            )
        self.modules = tuple(tiles)
        self.selected_module = None
        self.plan_review = None
        self.physical_confirmation_hash = None
        self.active_experiment_id = None
        self.progress_percent = 0
        self.state = LabDashboardState.READY
        self.status_code = "LAB_READY"

    def review(self, module_id: str, module_version: int) -> LabModuleTile:
        if self.state is not LabDashboardState.READY:
            raise LabDashboardRejectedError("LAB_DASHBOARD_NOT_READY")
        for tile in self.modules:
            if (tile.module_id, tile.module_version) == (module_id, module_version):
                self.selected_module = tile
                self.state = LabDashboardState.REVIEW
                self.status_code = "REVIEW_EXACT_PLAN"
                return tile
        raise LabDashboardRejectedError("LAB_MODULE_NOT_ADVERTISED")

    def apply_plan_review(self, plan: Mapping[str, object]) -> LabPlanReview:
        if self.state is not LabDashboardState.REVIEW or self.selected_module is None:
            raise LabDashboardRejectedError("LAB_MODULE_NOT_SELECTED")
        required = {
            "experiment_id",
            "module_id",
            "module_version",
            "targets",
            "fixture_ids",
            "parameters",
            "plan_hash",
            "execution_mode",
        }
        if set(plan) != required:
            raise LabDashboardRejectedError("LAB_PLAN_REVIEW_INVALID")
        parameters = plan["parameters"]
        if (
            plan["module_id"] != self.selected_module.module_id
            or plan["module_version"] != self.selected_module.module_version
            or plan["execution_mode"] != "simulation"
            or not isinstance(plan["experiment_id"], str)
            or not isinstance(plan["targets"], list)
            or not isinstance(plan["fixture_ids"], list)
            or not isinstance(parameters, Mapping)
            or not isinstance(plan["plan_hash"], str)
            or not plan["plan_hash"].startswith("sha256:")
        ):
            raise LabDashboardRejectedError("LAB_PLAN_REVIEW_INVALID")
        duration = parameters.get("duration_seconds")
        samples = parameters.get("sample_count")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or isinstance(samples, bool)
            or not isinstance(samples, int)
        ):
            raise LabDashboardRejectedError("LAB_PLAN_REVIEW_INVALID")
        review = LabPlanReview(
            experiment_id=plan["experiment_id"],
            module_id=self.selected_module.module_id,
            module_version=self.selected_module.module_version,
            target_count=len(plan["targets"]),
            fixture_count=len(plan["fixture_ids"]),
            duration_seconds=duration,
            sample_count=samples,
            plan_hash=plan["plan_hash"],
        )
        self.plan_review = review
        self.physical_confirmation_hash = None
        self.status_code = "REVIEW_EXACT_PLAN"
        return review

    def physical_confirmation_received(self, plan_hash: str) -> None:
        if self.state is not LabDashboardState.REVIEW or self.plan_review is None:
            raise LabDashboardRejectedError("LAB_PLAN_NOT_REVIEWED")
        if plan_hash != self.plan_review.plan_hash:
            raise LabDashboardRejectedError("LAB_CONFIRMATION_HASH_MISMATCH")
        self.physical_confirmation_hash = plan_hash
        self.status_code = "PHYSICAL_CONFIRMATION_ACCEPTED"

    def started(self, experiment_id: str) -> None:
        if self.state is not LabDashboardState.REVIEW:
            raise LabDashboardRejectedError("LAB_PLAN_NOT_REVIEWED")
        if (
            self.plan_review is None
            or self.physical_confirmation_hash != self.plan_review.plan_hash
        ):
            raise LabDashboardRejectedError("LAB_PHYSICAL_CONFIRMATION_REQUIRED")
        if not experiment_id.startswith("experiment:"):
            raise LabDashboardRejectedError("LAB_EXPERIMENT_ID_INVALID")
        self.active_experiment_id = experiment_id
        self.state = LabDashboardState.RUNNING
        self.status_code = "SIMULATION_RUNNING"

    def update_progress(
        self,
        experiment_id: str,
        *,
        progress_percent: int,
        metric_label: str,
        metric_value: int | float | str,
    ) -> None:
        if (
            self.state is not LabDashboardState.RUNNING
            or experiment_id != self.active_experiment_id
            or isinstance(progress_percent, bool)
            or not 0 <= progress_percent <= 100
            or metric_label
            not in {
                "samples_processed",
                "events_processed",
                "ber",
                "detected_events",
            }
        ):
            raise LabDashboardRejectedError("LAB_PROGRESS_INVALID")
        self.progress_percent = progress_percent
        self.primary_metric_label = metric_label
        self.primary_metric_value = metric_value

    def completed(self, experiment_id: str) -> None:
        if (
            self.state is not LabDashboardState.RUNNING
            or experiment_id != self.active_experiment_id
        ):
            raise LabDashboardRejectedError("LAB_COMPLETION_INVALID")
        self.progress_percent = 100
        self.state = LabDashboardState.RESULT
        self.status_code = "SIMULATION_COMPLETED"

    def cancelled(self, experiment_id: str) -> None:
        if (
            self.state is not LabDashboardState.RUNNING
            or experiment_id != self.active_experiment_id
        ):
            raise LabDashboardRejectedError("LAB_CANCEL_INVALID")
        self.state = LabDashboardState.CANCELLED
        self.status_code = "OPERATOR_CANCELLED"

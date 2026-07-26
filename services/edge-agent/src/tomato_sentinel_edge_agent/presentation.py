"""Trusted transformation of an edge capability report into bounded UI tiles."""

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from tomato_sentinel_experiments import ModuleRegistry


class LabDashboardPresentationRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class LabDashboardPresenter:
    def __init__(self, schema: Mapping[str, Any], modules: ModuleRegistry) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self._modules = modules

    def capabilities_view(self, report: Mapping[str, object]) -> Mapping[str, object]:
        if report.get("execution_mode") != "simulation":
            raise LabDashboardPresentationRejectedError("EDGE_MODE_UNSUPPORTED")
        raw_modules = report.get("modules")
        if not isinstance(raw_modules, list) or len(raw_modules) > 12:
            raise LabDashboardPresentationRejectedError("EDGE_MODULES_INVALID")
        tiles: list[dict[str, object]] = []
        for raw in raw_modules:
            if not isinstance(raw, Mapping):
                raise LabDashboardPresentationRejectedError("EDGE_MODULES_INVALID")
            module_id = raw.get("module_id")
            version = raw.get("module_version")
            if (
                not isinstance(module_id, str)
                or isinstance(version, bool)
                or not isinstance(version, int)
            ):
                raise LabDashboardPresentationRejectedError("EDGE_MODULES_INVALID")
            manifest = self._modules.get(module_id, version)
            tiles.append(
                {
                    "module_id": manifest.module_id,
                    "module_version": manifest.version,
                    "display_name": manifest.display_name,
                    "risk_class": manifest.risk_class.value,
                    "execution_mode": "simulation",
                }
            )
        view: dict[str, object] = {
            "contract_version": 1,
            "view_type": "lab.modules",
            "edge_id": report["edge_id"],
            "generated_at": report["generated_at"],
            "execution_mode": "simulation",
            "tiles": tiles,
        }
        try:
            self._validator.validate(view)
        except ValidationError as error:
            raise LabDashboardPresentationRejectedError(
                "DASHBOARD_VIEW_INVALID"
            ) from error
        return view

"""Transport-independent local edge boundary with a closed method registry."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from tomato_sentinel_experiments import (
    ExperimentProposalValidator,
    LocalExperimentModel,
    ModuleRegistry,
    canonical_capability_report_hash,
)

MAX_EDGE_REQUEST_BYTES = 8_192
MAX_IDEMPOTENCY_RECORDS = 256
_TYPED_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")


class LocalEdgeBoundaryRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class AuthenticatedLocalPeer:
    device_id: str
    organization_id: str
    authenticated: bool


class LocalEdgeApplication:
    """Application boundary; intentionally does not open a socket or LAN port."""

    def __init__(
        self,
        *,
        edge_id: str,
        organization_id: str,
        agent_version: str,
        modules: ModuleRegistry,
        proposal_model: LocalExperimentModel,
        proposal_validator: ExperimentProposalValidator,
    ) -> None:
        self._edge_id = edge_id
        self._organization_id = organization_id
        self._agent_version = agent_version
        self._modules = modules
        self._proposal_model = proposal_model
        self._proposal_validator = proposal_validator
        self._responses: dict[str, tuple[str, Mapping[str, object]]] = {}

    def handle(
        self,
        payload: Mapping[str, object],
        *,
        peer: AuthenticatedLocalPeer,
        received_at: datetime,
    ) -> Mapping[str, object]:
        self._verify_peer(peer)
        if received_at.tzinfo is None:
            raise LocalEdgeBoundaryRejectedError("EDGE_TIMEZONE_REQUIRED")
        encoded = _bounded_json(payload)
        required = {"contract_version", "request_id", "method", "body"}
        if set(payload) != required or payload.get("contract_version") != 1:
            raise LocalEdgeBoundaryRejectedError("EDGE_REQUEST_INVALID")
        request_id = payload["request_id"]
        method = payload["method"]
        body = payload["body"]
        if (
            not isinstance(request_id, str)
            or not request_id.startswith("edge-request:")
            or len(request_id) > 160
            or method not in {"edge.health", "edge.capabilities", "experiment.propose"}
            or not isinstance(body, Mapping)
        ):
            raise LocalEdgeBoundaryRejectedError("EDGE_REQUEST_INVALID")

        fingerprint = encoded.decode()
        existing = self._responses.get(request_id)
        if existing is not None:
            if existing[0] != fingerprint:
                raise LocalEdgeBoundaryRejectedError("EDGE_REQUEST_ID_REUSED")
            return dict(existing[1])

        if method == "edge.health":
            if body:
                raise LocalEdgeBoundaryRejectedError("EDGE_BODY_INVALID")
            response: Mapping[str, object] = {
                "contract_version": 1,
                "status": "ready",
                "execution_mode": "simulation",
                "network_listener": "disabled",
            }
        elif method == "edge.capabilities":
            if body:
                raise LocalEdgeBoundaryRejectedError("EDGE_BODY_INVALID")
            response = self._capability_report(received_at)
        else:
            if set(body) != {"prompt_id"}:
                raise LocalEdgeBoundaryRejectedError("EDGE_BODY_INVALID")
            prompt_id = body["prompt_id"]
            if (
                not isinstance(prompt_id, str)
                or not prompt_id.startswith("prompt:")
                or len(prompt_id) > 160
            ):
                raise LocalEdgeBoundaryRejectedError("EDGE_PROMPT_ID_INVALID")
            proposal = self._proposal_model.propose(prompt_id)
            response = self._proposal_validator.validate(proposal)

        if len(self._responses) >= MAX_IDEMPOTENCY_RECORDS:
            raise LocalEdgeBoundaryRejectedError("EDGE_IDEMPOTENCY_LIMIT_REACHED")
        self._responses[request_id] = (fingerprint, dict(response))
        return dict(response)

    def _verify_peer(self, peer: AuthenticatedLocalPeer) -> None:
        if not peer.authenticated:
            raise LocalEdgeBoundaryRejectedError("EDGE_PEER_UNAUTHENTICATED")
        if peer.organization_id != self._organization_id:
            raise LocalEdgeBoundaryRejectedError("EDGE_ORGANIZATION_MISMATCH")
        if _TYPED_IDENTIFIER.fullmatch(peer.device_id) is None:
            raise LocalEdgeBoundaryRejectedError("EDGE_DEVICE_ID_INVALID")

    def _capability_report(self, generated_at: datetime) -> Mapping[str, object]:
        valid_until = generated_at + timedelta(minutes=5)
        modules = [
            {
                "module_id": module.module_id,
                "module_version": module.version,
                "executor_id": module.executor_id,
                "capabilities": sorted(module.required_capabilities),
                "hardware": sorted(module.required_hardware),
            }
            for module in self._modules.modules
        ]
        payload: dict[str, object] = {
            "contract_version": 1,
            "edge_id": self._edge_id,
            "organization_id": self._organization_id,
            "agent_version": self._agent_version,
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
            "execution_mode": "simulation",
            "modules": modules,
        }
        payload["report_hash"] = canonical_capability_report_hash(payload)
        return payload


def _bounded_json(payload: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as error:
        raise LocalEdgeBoundaryRejectedError("EDGE_REQUEST_NOT_JSON") from error
    if len(encoded) > MAX_EDGE_REQUEST_BYTES:
        raise LocalEdgeBoundaryRejectedError("EDGE_REQUEST_TOO_LARGE")
    return encoded

"""Verified Cardputer dashboard adapter for the local edge application."""

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from tomato_sentinel_device_protocol import DeviceMessageVerifier

from .application import (
    AuthenticatedLocalPeer,
    LocalEdgeApplication,
    LocalEdgeBoundaryRejectedError,
)
from .presentation import LabDashboardPresenter


class DeviceLabDashboardRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class DeviceLabDashboardGateway:
    """Maps a signed Cardputer request to one closed local-edge method."""

    def __init__(
        self,
        verifier: DeviceMessageVerifier,
        application: LocalEdgeApplication,
        presenter: LabDashboardPresenter,
    ) -> None:
        self._verifier = verifier
        self._application = application
        self._presenter = presenter

    def handle(
        self,
        envelope: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> Mapping[str, object]:
        message = self._verifier.verify(envelope, received_at=received_at)
        if message.payload_type != "lab_dashboard_request":
            raise DeviceLabDashboardRejectedError("LAB_DASHBOARD_REQUEST_REQUIRED")
        payload = message.payload
        if payload["source_device_id"] != message.device_id:
            raise DeviceLabDashboardRejectedError("SOURCE_DEVICE_MISMATCH")
        requested_at = datetime.fromisoformat(
            cast(str, payload["requested_at"]).replace("Z", "+00:00")
        )
        if requested_at != message.sent_at:
            raise DeviceLabDashboardRejectedError("REQUEST_TIMESTAMP_MISMATCH")
        if payload["correlation_id"] != message.correlation_id:
            raise DeviceLabDashboardRejectedError("CORRELATION_ID_MISMATCH")

        action = cast(str, payload["action"])
        method = {
            "lab.dashboard.capabilities": "edge.capabilities",
            "lab.experiment.proposal": "experiment.propose",
        }.get(action)
        if method is None:
            raise DeviceLabDashboardRejectedError("LAB_DASHBOARD_ACTION_UNSUPPORTED")
        parameters = cast(Mapping[str, object], payload["parameters"])
        body: Mapping[str, object] = (
            {}
            if method == "edge.capabilities"
            else {"prompt_id": parameters["prompt_id"]}
        )
        try:
            response = self._application.handle(
                {
                    "contract_version": 1,
                    "request_id": payload["request_id"],
                    "method": method,
                    "body": body,
                },
                peer=AuthenticatedLocalPeer(
                    device_id=message.device_id,
                    organization_id=cast(str, payload["organization_id"]),
                    authenticated=True,
                ),
                received_at=received_at,
            )
            if method == "edge.capabilities":
                return self._presenter.capabilities_view(response)
            return response
        except LocalEdgeBoundaryRejectedError as error:
            raise DeviceLabDashboardRejectedError(error.reason_code) from error

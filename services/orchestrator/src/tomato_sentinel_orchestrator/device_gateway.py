"""Authenticated device boundaries for structured commands and cancellation."""

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from tomato_sentinel_device_protocol import DeviceMessageVerifier

from .asset_inventory import AssetInventoryOutcome, AssetInventoryService
from .discovery import DiscoveryOutcome, PassiveDiscoveryService
from .models import CommandOutcome, ExecutionContext
from .monitoring_models import MonitoringOutcome
from .monitoring_service import MonitoringService
from .service import CameraStatusService


class DeviceTextCommandRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class DeviceTextCommandGateway:
    """Dispatch one verified command through a fixed registered action map."""

    def __init__(
        self,
        verifier: DeviceMessageVerifier,
        *,
        camera_status: CameraStatusService,
        monitoring: MonitoringService,
        asset_inventory: AssetInventoryService,
        discovery: PassiveDiscoveryService,
    ) -> None:
        self._verifier = verifier
        self._camera_status = camera_status
        self._monitoring = monitoring
        self._asset_inventory = asset_inventory
        self._discovery = discovery

    def handle(
        self,
        envelope: Mapping[str, object],
        context: ExecutionContext,
        *,
        received_at: datetime,
    ) -> CommandOutcome | MonitoringOutcome | AssetInventoryOutcome | DiscoveryOutcome:
        message = self._verifier.verify(envelope, received_at=received_at)
        if message.payload_type != "text_command":
            raise DeviceTextCommandRejectedError("TEXT_COMMAND_REQUIRED")
        if message.device_id != context.device.device_id:
            raise DeviceTextCommandRejectedError("DEVICE_CONTEXT_MISMATCH")

        payload = message.payload
        if payload["source_device_id"] != message.device_id:
            raise DeviceTextCommandRejectedError("SOURCE_DEVICE_MISMATCH")
        requested_at = datetime.fromisoformat(
            cast(str, payload["requested_at"]).replace("Z", "+00:00")
        )
        if requested_at != message.sent_at:
            raise DeviceTextCommandRejectedError("COMMAND_TIMESTAMP_MISMATCH")
        expected_correlation_id = cast(
            str,
            payload.get("correlation_id", payload["command_id"]),
        )
        if expected_correlation_id != message.correlation_id:
            raise DeviceTextCommandRejectedError("CORRELATION_ID_MISMATCH")

        action = cast(str, payload["action"])
        if action == "camera.status":
            return self._camera_status.execute(
                payload,
                context,
                evaluated_at=received_at,
            )
        if action == "camera.monitor":
            return self._monitoring.start(
                payload,
                context,
                evaluated_at=received_at,
            )
        if action == "asset.list":
            return self._asset_inventory.execute(
                payload,
                context,
                evaluated_at=received_at,
            )
        if action == "network.passive_discovery":
            return self._discovery.start(
                payload,
                context,
                evaluated_at=received_at,
            )
        raise DeviceTextCommandRejectedError("ACTION_NOT_SUPPORTED")


class DeviceCancelGateway:
    def __init__(self, verifier: DeviceMessageVerifier) -> None:
        self._verifier = verifier

    def handle(
        self,
        envelope: Mapping[str, object],
        context: ExecutionContext,
        monitoring: MonitoringService,
        *,
        received_at: datetime,
        discovery: PassiveDiscoveryService | None = None,
    ) -> MonitoringOutcome | DiscoveryOutcome:
        message = self._verifier.verify(envelope, received_at=received_at)
        if message.payload_type != "cancel_request":
            raise ValueError("device message is not a cancellation request")
        if message.device_id != context.device.device_id:
            raise PermissionError("device identity does not match execution context")
        requested_at = datetime.fromisoformat(
            cast(str, message.payload["requested_at"]).replace("Z", "+00:00")
        )
        if requested_at != message.sent_at:
            raise ValueError("cancellation timestamp does not match envelope")
        job_id = cast(str, message.payload["job_id"])
        if job_id.startswith("job:discovery-"):
            if discovery is None:
                raise ValueError("discovery cancellation route is unavailable")
            return discovery.cancel(
                job_id,
                context,
                evaluated_at=received_at,
            )
        return monitoring.cancel(
            job_id,
            context,
            evaluated_at=received_at,
        )

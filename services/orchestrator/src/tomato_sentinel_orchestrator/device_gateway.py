"""Authenticated device boundary for fixed physical cancellation."""

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from tomato_sentinel_device_protocol import DeviceMessageVerifier

from .models import ExecutionContext
from .monitoring_models import MonitoringOutcome
from .monitoring_service import MonitoringService


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
    ) -> MonitoringOutcome:
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
        return monitoring.cancel(
            cast(str, message.payload["job_id"]),
            context,
            evaluated_at=received_at,
        )

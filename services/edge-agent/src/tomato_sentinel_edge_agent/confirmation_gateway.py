"""Conversion of a signed physical Cardputer confirmation into policy input."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from tomato_sentinel_device_protocol import DeviceMessageVerifier
from tomato_sentinel_policy import Confirmation, ConfirmationMethod


class DeviceLabConfirmationRejectedError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class BoundLabOperator:
    actor_id: str
    organization_id: str


class DeviceLabConfirmationGateway:
    """Issues a 60-second policy confirmation only after envelope verification."""

    def __init__(
        self,
        verifier: DeviceMessageVerifier,
        operator_bindings: Mapping[str, BoundLabOperator],
    ) -> None:
        self._verifier = verifier
        self._operator_bindings = dict(operator_bindings)

    def handle(
        self,
        envelope: Mapping[str, object],
        *,
        received_at: datetime,
    ) -> Confirmation:
        message = self._verifier.verify(envelope, received_at=received_at)
        if message.payload_type != "lab_plan_confirmation":
            raise DeviceLabConfirmationRejectedError("LAB_PLAN_CONFIRMATION_REQUIRED")
        payload = message.payload
        if payload["source_device_id"] != message.device_id:
            raise DeviceLabConfirmationRejectedError("SOURCE_DEVICE_MISMATCH")
        confirmed_at = datetime.fromisoformat(
            cast(str, payload["confirmed_at"]).replace("Z", "+00:00")
        )
        if confirmed_at != message.sent_at:
            raise DeviceLabConfirmationRejectedError("CONFIRMATION_TIMESTAMP_MISMATCH")
        if payload["correlation_id"] != message.correlation_id:
            raise DeviceLabConfirmationRejectedError("CORRELATION_ID_MISMATCH")
        binding = self._operator_bindings.get(message.device_id)
        if binding is None:
            raise DeviceLabConfirmationRejectedError("DEVICE_OPERATOR_NOT_BOUND")
        if (
            payload["actor_id"] != binding.actor_id
            or payload["organization_id"] != binding.organization_id
        ):
            raise DeviceLabConfirmationRejectedError("OPERATOR_BINDING_MISMATCH")
        return Confirmation(
            actor_id=binding.actor_id,
            device_id=message.device_id,
            plan_hash=cast(str, payload["plan_hash"]),
            method=ConfirmationMethod.PHYSICAL,
            valid_until=received_at + timedelta(seconds=60),
        )

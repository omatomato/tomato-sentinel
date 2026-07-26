"""Public API for the simulated Cardputer device protocol."""

from .audio import (
    MAXIMUM_CAPTURE_DURATION_MS,
    MAXIMUM_ENCODED_AUDIO_BYTES,
    AudioCaptureLimitError,
    AudioCaptureMetadata,
    AudioCaptureState,
    PushToTalkRecorder,
)
from .board_profiles import load_board_profile
from .models import (
    BoardProfile,
    ProfileState,
    ProvisionedDevice,
    VerifiedDeviceMessage,
)
from .protocol import (
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    sign_envelope,
)
from .simulator import CardputerSimulator

__all__ = [
    "MAXIMUM_CAPTURE_DURATION_MS",
    "MAXIMUM_ENCODED_AUDIO_BYTES",
    "AudioCaptureLimitError",
    "AudioCaptureMetadata",
    "AudioCaptureState",
    "BoardProfile",
    "CardputerSimulator",
    "DeviceMessageRejectedError",
    "DeviceMessageVerifier",
    "DeviceProtocolValidator",
    "DeviceRegistry",
    "ProfileState",
    "ProvisionedDevice",
    "PushToTalkRecorder",
    "VerifiedDeviceMessage",
    "load_board_profile",
    "sign_envelope",
]

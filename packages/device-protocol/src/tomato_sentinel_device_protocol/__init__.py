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
from .command_composer import (
    MAXIMUM_MENU_CAMERAS,
    MAXIMUM_MENU_INVENTORIES,
    MAXIMUM_MENU_NETWORKS,
    CameraMenuEntry,
    CommandCompositionRejectedError,
    CommandMenuAction,
    InventoryMenuEntry,
    NetworkMenuEntry,
    RegisteredCommandComposer,
)
from .lab_dashboard import (
    MAXIMUM_LAB_MODULE_TILES,
    CardputerLabDashboard,
    LabDashboardRejectedError,
    LabDashboardState,
    LabModuleTile,
    LabPlanReview,
)
from .models import (
    BoardProfile,
    DeviceIdentityState,
    DeviceIdentityStatus,
    ProfileState,
    ProvisionedDevice,
    VerifiedDeviceMessage,
)
from .protocol import (
    MAXIMUM_KEY_ROTATIONS_PER_DEVICE,
    DeviceMessageRejectedError,
    DeviceMessageVerifier,
    DeviceProtocolValidator,
    DeviceRegistry,
    DeviceRegistryChangeRejectedError,
    sign_envelope,
)
from .simulator import CardputerSimulator

__all__ = [
    "MAXIMUM_CAPTURE_DURATION_MS",
    "MAXIMUM_ENCODED_AUDIO_BYTES",
    "MAXIMUM_KEY_ROTATIONS_PER_DEVICE",
    "MAXIMUM_LAB_MODULE_TILES",
    "MAXIMUM_MENU_CAMERAS",
    "MAXIMUM_MENU_INVENTORIES",
    "MAXIMUM_MENU_NETWORKS",
    "AudioCaptureLimitError",
    "AudioCaptureMetadata",
    "AudioCaptureState",
    "BoardProfile",
    "CameraMenuEntry",
    "CardputerLabDashboard",
    "CardputerSimulator",
    "CommandCompositionRejectedError",
    "CommandMenuAction",
    "DeviceIdentityState",
    "DeviceIdentityStatus",
    "DeviceMessageRejectedError",
    "DeviceMessageVerifier",
    "DeviceProtocolValidator",
    "DeviceRegistry",
    "DeviceRegistryChangeRejectedError",
    "InventoryMenuEntry",
    "LabDashboardRejectedError",
    "LabDashboardState",
    "LabModuleTile",
    "LabPlanReview",
    "NetworkMenuEntry",
    "ProfileState",
    "ProvisionedDevice",
    "PushToTalkRecorder",
    "RegisteredCommandComposer",
    "VerifiedDeviceMessage",
    "load_board_profile",
    "sign_envelope",
]

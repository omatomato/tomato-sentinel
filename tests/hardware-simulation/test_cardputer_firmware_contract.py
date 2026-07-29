import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
SKETCH_DIR = ROOT / "firmware/cardputer/app/TomatoSentinel"
SKETCH = SKETCH_DIR / "TomatoSentinel.ino"
DISPLAY_PROFILE = SKETCH_DIR / "OriginalCardputerDisplay.h"
KEYBOARD_PROFILE = SKETCH_DIR / "OriginalCardputerKeyboard.h"
LOCAL_DRAFT = SKETCH_DIR / "LocalDraft.h"
UI = SKETCH_DIR / "TomatoSentinelUi.h"
SAFE_BOOT_GUARD = SKETCH_DIR / "SafeBootGuard.h"
RUNTIME_WRITE_GUARDS = SKETCH_DIR / "RuntimeWriteGuards.cpp"
SAFE_BUILD = ROOT / "firmware/cardputer/build-safe.sh"


def test_original_cardputer_build_profile_is_exactly_pinned() -> None:
    project = (SKETCH_DIR / "sketch.yaml").read_text()

    assert "default_profile: original" in project
    assert "fqbn: esp32:esp32:m5stack_cardputer:" in project
    assert "FlashMode=qio" in project
    assert "FlashSize=8M" in project
    assert "USBMode=hwcdc" in project
    assert "CDCOnBoot=cdc" in project
    assert "PSRAM=disabled" in project
    assert "PartitionScheme=default_8MB" in project
    assert "UploadSpeed=115200" in project
    assert "EraseFlash=none" in project
    assert "platform: esp32:esp32 (3.3.10)" in project
    assert (
        "https://espressif.github.io/arduino-esp32/package_esp32_index.json" in project
    )
    assert "- M5GFX (0.2.26)" in project
    assert "- M5Unified (" not in project
    assert "- M5Cardputer (" not in project


def test_firmware_fails_closed_and_keeps_cancel_visible() -> None:
    source = SKETCH.read_text()
    ui = UI.read_text()
    loop_source = source[source.index("void loop()") :]

    assert "#error" in source
    assert "TOMATO_TARGET_CARDPUTER_ORIGINAL" in source
    assert "ARDUINO_M5STACK_CARDPUTER" in source
    assert "TOMATO_RUNTIME_WRITE_GUARDS" in source
    assert "NO_GLOBAL_SERIAL" in source
    assert "ARDUINO_USB_MODE" in source
    assert "ARDUINO_USB_CDC_ON_BOOT" in source
    assert "HWCDCSerial.begin(115200);" in source
    assert "\n  Serial.begin(" not in source
    assert 'kOperatingProfile[] = "ASSISTANT"' in source
    assert "TomatoSentinelUi ui(display, kOperatingProfile);" in source
    assert "display_.print(profile_);" in ui
    assert "G0: CANCEL" in ui
    assert loop_source.index("cancelWasPressed()") < loop_source.index(
        "delay(kLoopDelayMs);"
    )


def test_display_profile_only_drives_original_cardputer_lcd_pins() -> None:
    source = SKETCH.read_text()
    display = DISPLAY_PROFILE.read_text()

    expected_display_pins = {
        "kMosiPin": 35,
        "kSclkPin": 36,
        "kDcPin": 34,
        "kChipSelectPin": 37,
        "kResetPin": 33,
        "kBacklightPin": 38,
    }
    for name, pin in expected_display_pins.items():
        assert f"static constexpr int {name} = {pin};" in display

    assert "OriginalCardputerDisplay" in display
    assert "lgfx::Panel_ST7789" in display
    assert "M5GFX display" not in display
    assert "AUTODETECT" not in display
    assert "NVS" in display  # The comment documents why automatic detection is absent.
    assert "pinMode(kCancelButtonPin, INPUT);" in source
    assert "pinMode(kMicrophoneDataPin, INPUT);" in source
    assert "pinMode(kMicrophoneDataPin, OUTPUT)" not in source


def test_initial_firmware_has_no_network_or_large_feature_includes() -> None:
    source = (
        SKETCH.read_text()
        + DISPLAY_PROFILE.read_text()
        + KEYBOARD_PROFILE.read_text()
        + UI.read_text()
        + SAFE_BOOT_GUARD.read_text()
    )

    prohibited = [
        "#include <M5Unified.h>",
        "#include <M5Cardputer.h>",
        "#include <WiFi.h>",
        "#include <WebServer.h>",
        "#include <BLE",
        "esp_wifi_",
        "M5.begin",
        "M5.getBoard",
        "M5.update",
        "M5.BtnA",
    ]
    assert not any(item in source for item in prohibited)


def test_original_keyboard_electrical_directions_are_fixed_and_bounded() -> None:
    source = SKETCH.read_text()
    keyboard = KEYBOARD_PROFILE.read_text()

    assert "kSelectorPins[3] = {8, 9, 11}" in keyboard
    assert "kSensePins[7] = {13, 15, 3, 4, 5, 6, 7}" in keyboard
    assert "pinMode(pin, OUTPUT);" in keyboard
    assert "pinMode(pin, INPUT_PULLUP);" in keyboard
    assert keyboard.index("digitalWrite(pin, LOW);") < keyboard.index(
        "pinMode(pin, OUTPUT);"
    )
    assert "for (uint8_t selector = 0; selector < 8; ++selector)" in keyboard
    assert "for (uint8_t sense = 0; sense < 7; ++sense)" in keyboard
    assert "kSelectorSettleUs = 5" in keyboard
    assert "kDebounceMs = 30" in keyboard
    assert "selectRow(0);" in keyboard
    assert "keyboard.begin(millis());" in source
    assert source.index("if (safe_mode_latched)") < source.index(
        "keyboard.begin(millis());"
    )


def test_local_keyboard_input_is_denied_by_default_and_never_transmitted() -> None:
    source = SKETCH.read_text()
    keyboard = KEYBOARD_PROFILE.read_text()
    draft = LOCAL_DRAFT.read_text()
    ui = UI.read_text()
    loop_source = source[source.index("void loop()") :]

    assert "kMaximumLength = 64" in draft
    assert "volatile char* cursor = text_;" in draft
    assert "EventKind::ambiguous" in keyboard
    assert "selected_count != 1" in keyboard
    combined = source + ui
    assert "MULTI-KEY DENIED" in combined
    assert "LIMIT 64 / INPUT DENIED" in combined
    assert "DISCARDED / NO ACTION" in combined
    assert "RAM ONLY / NOT SENT" in combined
    assert "local_draft.clear();" in source
    assert "cancelWasPressed() || button_raw_pressed" in loop_source
    assert "LOCAL DRAFT discarded_bytes=%u action=none" in source
    assert "HWCDCSerial.print(local_draft" not in source
    assert "HWCDCSerial.printf(local_draft" not in source
    assert loop_source.index("cancelWasPressed()") < loop_source.index(
        "keyboard.poll(millis())"
    )
    assert (
        "if (!safe_mode_latched && !cancel_requested && !kInteropEvidenceBuild) {"
        in loop_source
    )


def test_keyboard_mapping_has_compile_time_negative_controls() -> None:
    keyboard = KEYBOARD_PROFILE.read_text()

    assert "static_assert(kOriginalKeyboardBacktick.character == '`');" in keyboard
    assert "static_assert(kOriginalKeyboardDigitOne.character == '1');" in keyboard
    assert "static_assert(kOriginalKeyboardSpace.character == ' ');" in keyboard
    assert "kOriginalKeyboardChord.kind" in keyboard
    assert "OriginalCardputerKeyboard::EventKind::ambiguous" in keyboard
    assert "kOriginalKeyboardShift.kind" in keyboard
    assert "OriginalCardputerKeyboard::EventKind::shift" in keyboard
    assert "shiftedCharacter('a') == 'A'" in keyboard
    assert "shiftedCharacter('1') == '!'" in keyboard
    assert "shiftedCharacter('/') == '?'" in keyboard


def test_one_shot_shift_is_visible_bounded_and_cancelled() -> None:
    source = SKETCH.read_text()
    ui = UI.read_text()

    assert "bool one_shot_shift_armed = false;" in source
    assert "one_shot_shift_armed = !one_shot_shift_armed;" in source
    assert "SHIFT ARMED / NEXT KEY" in source
    assert "SHIFT DISARMED" in source
    assert "shiftedCharacter(event.character)" in source
    assert source.count("one_shot_shift_armed = false;") >= 3
    assert "bool shift_armed" in ui
    assert "shift_armed ? kWarning : kInput" in ui


def test_compact_ui_keeps_profile_and_safety_states_visible() -> None:
    ui = UI.read_text()

    required_states = [
        "DEVICE READY",
        "LOCAL CONSOLE",
        "OFFLINE  /  RAM ONLY",
        "LOCAL DRAFT",
        "FAIL-SAFE MODE",
        "RECOVERY",
        "CANCEL REQUESTED",
        "SAFE STATE",
        "INPUT LOCKED",
    ]
    for state in required_states:
        assert state in ui

    assert "display_.print(profile_);" in ui
    assert "fillRoundRect(8, 35, 224, 68, 8" in ui
    assert "fillRect(0, 108, display_.width(), 27" in ui
    assert "kTomato" in ui
    assert "kSafe" in ui
    assert "kWarning" in ui
    assert "kDanger" in ui
    assert "new " not in ui
    assert "malloc" not in ui
    assert "Sprite" not in ui

    footer_pairs = [
        ("G0: CANCEL", "TYPE TO START"),
        ("G0: CLEAR", "ENTER: DISCARD"),
        ("LOCKED", "G0+USB RECOVERY"),
        ("INPUT LOCKED", "RESET TO CONTINUE"),
    ]
    for left_text, right_text in footer_pairs:
        assert left_text in ui
        assert right_text in ui
        left_end = 20 + len(left_text) * 6
        right_start = 240 - len(right_text) * 6 - 8
        assert left_end + 8 <= right_start


def test_fail_safe_guard_is_flash_free_and_fails_closed() -> None:
    source = SKETCH.read_text()
    ui = UI.read_text()
    guard = SAFE_BOOT_GUARD.read_text()
    runtime_guards = RUNTIME_WRITE_GUARDS.read_text()
    build = SAFE_BUILD.read_text()

    assert "RTC_NOINIT_ATTR SafeBootGuard::State rtc_boot_guard;" in source
    assert "enableLoopWDT();" in source
    assert "esp_task_wdt_status(nullptr) == ESP_OK" in source
    assert "safe_mode_latched = safe_mode_latched || !loop_watchdog_ready;" in source
    assert "kHealthyBootAfterMs = 5000" in source
    assert "FAIL-SAFE MODE" in ui
    assert "G0+USB RECOVERY" in ui
    assert "kSafeModeThreshold = 2" in guard
    assert "static_assert(kSecondFailedBoot.enter_safe_mode);" in guard
    assert "static_assert(kRecoveredBoot.unfinished_boots == 0);" in guard
    assert "verifyRollbackLater()" in runtime_guards
    assert "return true;" in runtime_guards
    assert "__wrap_nvs_flash_init()" in runtime_guards
    assert "return ESP_ERR_NOT_SUPPORTED;" in runtime_guards
    assert "-DTOMATO_RUNTIME_WRITE_GUARDS=1" in build
    assert "-DNO_GLOBAL_SERIAL" in build
    assert "-DSerial=HWCDCSerial" in build
    assert "compiler.cpp.extra_flags=" in build
    assert "build.extra_flags=" not in build
    assert "export SOURCE_DATE_EPOCH=0" in build
    required_link_guards = [
        "nvs_flash_init",
        "esp_partition_write",
        "esp_partition_write_raw",
        "esp_partition_erase_range",
        "esp_flash_write",
        "esp_flash_write_encrypted",
        "esp_flash_erase_region",
    ]
    for symbol in required_link_guards:
        assert f"__wrap_{symbol}" in runtime_guards
        assert f"-Wl,--wrap={symbol}" in build
    assert "--upload" not in build
    assert "write-flash" not in build

    combined = source + guard
    prohibited_mutations = [
        "Preferences",
        "nvs_set",
        "nvs_erase",
        "nvs_commit",
        "esp_ota_",
        "esp_partition_write",
        "esp_flash_write",
        "esp_flash_erase",
        "esp_efuse",
    ]
    assert not any(item in combined for item in prohibited_mutations)


def test_reviewed_original_user_demo_is_cataloged_but_not_integrated() -> None:
    catalog = (ROOT / "config/upstream/software-catalog.yaml").read_text()

    assert "project_id: m5cardputer-userdemo-v0-9" in catalog
    assert "commit: b0c678d5f19d9c2c6d7c362a1a478369994cadc6" in catalog
    assert "release: V0.9" in catalog
    assert "mode: reference_only" in catalog


def test_community_firmware_research_is_exact_and_not_integrated() -> None:
    catalog = (ROOT / "config/upstream/software-catalog.yaml").read_text()
    review = (ROOT / "docs/hardware/cardputer-community-project-review.md").read_text()

    expected_references = {
        "bruce-firmware-1-16": "59e83bfbd8a63a6b67ea23498e15c710a1ed9657",
        "evil-m5project": "78f0289a8dbdd849242a35cd763410c360cb16e5",
        "m5launcher-2-7-2": "01cf31d9fe1ff8c1ac774b344efb5b05d21016de",
    }
    for project_id, commit in expected_references.items():
        assert f"project_id: {project_id}" in catalog
        assert f"commit: {commit}" in catalog
        assert commit in review

    reviewed_entries = catalog[catalog.index("project_id: bruce-firmware-1-16") :]
    assert reviewed_entries.count("mode: reference_only") >= 3
    assert reviewed_entries.count("status: rejected") >= 3
    assert "No upstream application code was copied or executed." in review


def test_original_profile_contains_complete_documented_keyboard_pin_set() -> None:
    profile = json.loads(
        (
            ROOT / "firmware/cardputer/board_profiles/cardputer.original.v1.json"
        ).read_text()
    )

    assert profile["interfaces"]["keyboard"]["pins"] == {
        "selector_a0": 8,
        "selector_a1": 9,
        "selector_a2": 11,
        "sense_0": 13,
        "sense_1": 15,
        "sense_2": 3,
        "sense_3": 4,
        "sense_4": 5,
        "sense_5": 6,
        "sense_6": 7,
    }

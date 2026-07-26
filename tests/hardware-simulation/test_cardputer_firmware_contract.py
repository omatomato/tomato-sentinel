from pathlib import Path

ROOT = Path(__file__).parents[2]
SKETCH_DIR = ROOT / "firmware/cardputer/app/TomatoSentinel"
SKETCH = SKETCH_DIR / "TomatoSentinel.ino"


def test_original_cardputer_build_profile_is_exactly_pinned() -> None:
    project = (SKETCH_DIR / "sketch.yaml").read_text()

    assert "default_profile: original" in project
    assert "fqbn: esp32:esp32:esp32s3:" in project
    assert "FlashSize=8M" in project
    assert "PSRAM=disabled" in project
    assert "platform: esp32:esp32 (3.3.10)" in project
    assert (
        "https://espressif.github.io/arduino-esp32/package_esp32_index.json" in project
    )
    assert "- M5Unified (0.2.19)" in project
    assert "- M5GFX (0.2.26)" in project
    assert "M5Cardputer" not in project


def test_firmware_fails_closed_and_keeps_cancel_visible() -> None:
    source = SKETCH.read_text()
    loop_source = source[source.index("void loop()") :]

    assert "#error" in source
    assert "TOMATO_TARGET_CARDPUTER_ORIGINAL" in source
    assert "board_M5Cardputer" in source
    assert "PROFILE: " in source
    assert "ASSISTANT" in source
    assert "G0: CANCEL" in source
    assert "CAPABILITIES WITHHELD" in source
    assert (
        loop_source.index("M5.update();")
        < loop_source.index("M5.BtnA.wasPressed()")
        < loop_source.index("delay(kLoopDelayMs);")
    )


def test_initial_firmware_has_no_network_or_large_feature_includes() -> None:
    source = SKETCH.read_text()

    prohibited = [
        "#include <M5Cardputer.h>",
        "#include <WiFi.h>",
        "#include <WebServer.h>",
        "#include <BLE",
        "esp_wifi_",
    ]
    assert not any(item in source for item in prohibited)

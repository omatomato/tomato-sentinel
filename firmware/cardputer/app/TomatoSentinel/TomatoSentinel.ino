#include <Arduino.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <esp_task_wdt.h>

#include "LocalDraft.h"
#include "OriginalCardputerDisplay.h"
#include "OriginalCardputerKeyboard.h"
#include "SafeBootGuard.h"
#include "TomatoSentinelUi.h"

#if !defined(TOMATO_TARGET_CARDPUTER_ORIGINAL) || \
    TOMATO_TARGET_CARDPUTER_ORIGINAL != 1
#error "Build refused: select the explicit original Cardputer target"
#endif

#if !defined(ARDUINO_M5STACK_CARDPUTER)
#error "Build refused: select esp32:esp32:m5stack_cardputer"
#endif

#if !defined(TOMATO_RUNTIME_WRITE_GUARDS) || TOMATO_RUNTIME_WRITE_GUARDS != 1
#error "Build refused: runtime flash-write guards are mandatory"
#endif

#if !defined(NO_GLOBAL_SERIAL)
#error "Build refused: hardware UART globals must be disabled"
#endif

#if !defined(ARDUINO_USB_MODE) || ARDUINO_USB_MODE != 1 || \
    !defined(ARDUINO_USB_CDC_ON_BOOT) || ARDUINO_USB_CDC_ON_BOOT != 1
#error "Build refused: select hardware USB CDC/JTAG logging"
#endif

namespace {

constexpr char kFirmwareVersion[] = "0.2.2-poc";
constexpr char kBoardProfile[] = "board-profile:cardputer-original-v1";
constexpr char kOperatingProfile[] = "ASSISTANT";
constexpr uint8_t kCancelButtonPin = 0;
constexpr uint8_t kMicrophoneDataPin = 46;
constexpr uint8_t kOperatingBrightness = 64;
constexpr uint32_t kLoopDelayMs = 10;
constexpr uint32_t kDebounceMs = 30;
constexpr uint32_t kHealthyBootAfterMs = 5000;

OriginalCardputerDisplay display;
TomatoSentinelUi ui(display, kOperatingProfile);
OriginalCardputerKeyboard keyboard;
LocalDraft local_draft;
RTC_NOINIT_ATTR SafeBootGuard::State rtc_boot_guard;
bool cancel_requested = false;
bool safe_mode_latched = false;
bool boot_marked_healthy = false;
bool button_raw_pressed = false;
bool button_stable_pressed = false;
bool one_shot_shift_armed = false;
uint32_t button_changed_at_ms = 0;
uint32_t boot_started_at_ms = 0;

SafeBootGuard::ResetClass classifyReset(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:
    case ESP_RST_EXT:
    case ESP_RST_DEEPSLEEP:
      return SafeBootGuard::ResetClass::clean_start;
    default:
      return SafeBootGuard::ResetClass::unfinished_start;
  }
}

void handleKeyboardEvent(const OriginalCardputerKeyboard::Event& event) {
  using EventKind = OriginalCardputerKeyboard::EventKind;

  switch (event.kind) {
    case EventKind::none:
      return;
    case EventKind::character: {
      const char character =
          one_shot_shift_armed
              ? OriginalCardputerKeyboard::shiftedCharacter(event.character)
              : event.character;
      one_shot_shift_armed = false;
      if (local_draft.append(character)) {
        ui.drawDraft(local_draft, "RAM ONLY / NOT SENT",
                     TomatoSentinelUi::Tone::safe, one_shot_shift_armed);
      } else {
        ui.drawDraft(local_draft, "LIMIT 64 / INPUT DENIED",
                     TomatoSentinelUi::Tone::danger, one_shot_shift_armed);
      }
      return;
    }
    case EventKind::backspace:
      local_draft.backspace();
      ui.drawDraft(local_draft, "RAM ONLY / NOT SENT",
                   TomatoSentinelUi::Tone::safe, one_shot_shift_armed);
      return;
    case EventKind::enter: {
      const size_t discarded_length = local_draft.length();
      one_shot_shift_armed = false;
      local_draft.clear();
      ui.drawDraft(local_draft, "DISCARDED / NO ACTION",
                   TomatoSentinelUi::Tone::safe, one_shot_shift_armed);
      HWCDCSerial.printf("LOCAL DRAFT discarded_bytes=%u action=none\n",
                         discarded_length);
      return;
    }
    case EventKind::shift:
      one_shot_shift_armed = !one_shot_shift_armed;
      ui.drawDraft(local_draft,
                   one_shot_shift_armed ? "SHIFT ARMED / NEXT KEY"
                                        : "SHIFT DISARMED",
                   one_shot_shift_armed ? TomatoSentinelUi::Tone::warning
                                        : TomatoSentinelUi::Tone::muted,
                   one_shot_shift_armed);
      return;
    case EventKind::ignored:
      ui.drawDraft(local_draft, "MODIFIER IGNORED",
                   TomatoSentinelUi::Tone::muted, one_shot_shift_armed);
      return;
    case EventKind::ambiguous:
      ui.drawDraft(local_draft, "MULTI-KEY DENIED",
                   TomatoSentinelUi::Tone::danger, one_shot_shift_armed);
      return;
  }
}

bool cancelWasPressed() {
  const bool pressed_now = digitalRead(kCancelButtonPin) == LOW;
  const uint32_t now = millis();

  if (pressed_now != button_raw_pressed) {
    button_raw_pressed = pressed_now;
    button_changed_at_ms = now;
  }

  if (button_stable_pressed != button_raw_pressed &&
      now - button_changed_at_ms >= kDebounceMs) {
    button_stable_pressed = button_raw_pressed;
    return button_stable_pressed;
  }

  return false;
}

}  // namespace

void setup() {
  // GPIO0 already has a 10 kOhm external pull-up on the original Cardputer.
  // GPIO46 is microphone DATA and must never be driven by this proof of concept.
  pinMode(kCancelButtonPin, INPUT);
  pinMode(kMicrophoneDataPin, INPUT);
  button_raw_pressed = digitalRead(kCancelButtonPin) == LOW;
  button_stable_pressed = button_raw_pressed;
  button_changed_at_ms = millis();

  HWCDCSerial.begin(115200);

  const esp_reset_reason_t reset_reason = esp_reset_reason();
  const SafeBootGuard::Decision boot_decision =
      SafeBootGuard::begin(rtc_boot_guard, classifyReset(reset_reason));
  rtc_boot_guard = boot_decision.next;
  safe_mode_latched = boot_decision.enter_safe_mode;

  // Arduino-ESP32 initializes a 5-second panic/reset task watchdog, but the
  // loop task is only watched after this explicit subscription.
  enableLoopWDT();
  const bool loop_watchdog_ready = esp_task_wdt_status(nullptr) == ESP_OK;
  safe_mode_latched = safe_mode_latched || !loop_watchdog_ready;

  // Keep the backlight dark during the bounded, explicit panel initialization.
  if (!display.init()) {
    HWCDCSerial.println(
        "FATAL display initialization failed; capabilities withheld");
    while (true) {
      delay(kLoopDelayMs);
    }
  }

  display.setRotation(1);
  display.fillScreen(TFT_BLACK);
  display.setBrightness(kOperatingBrightness);
  if (safe_mode_latched) {
    ui.drawSafeMode(rtc_boot_guard.unfinished_boots);
  } else {
    keyboard.begin(millis());
    ui.drawReady();
  }
  boot_started_at_ms = millis();

  HWCDCSerial.printf(
      "READY firmware=%s board_profile=%s profile=%s reset_reason=%d "
      "safe_mode=%s loop_wdt=%s unfinished_boots=%u\n",
      kFirmwareVersion,
      kBoardProfile,
      kOperatingProfile,
      static_cast<int>(reset_reason),
      safe_mode_latched ? "latched" : "off",
      loop_watchdog_ready ? "ready" : "failed",
      rtc_boot_guard.unfinished_boots);
}

void loop() {
  // Physical cancellation is sampled before ordinary UI work.
  const bool cancel_pressed = cancelWasPressed() || button_raw_pressed;
  if (cancel_pressed && !cancel_requested) {
    cancel_requested = true;
    one_shot_shift_armed = false;
    local_draft.clear();
    HWCDCSerial.println("CANCEL REQUESTED status=no_active_job");
    ui.drawCancelled();
  }

  if (!safe_mode_latched && !cancel_requested) {
    handleKeyboardEvent(keyboard.poll(millis()));
  }

  if (!boot_marked_healthy &&
      millis() - boot_started_at_ms >= kHealthyBootAfterMs) {
    rtc_boot_guard = SafeBootGuard::markHealthy(rtc_boot_guard);
    boot_marked_healthy = true;
    HWCDCSerial.printf(
        "BOOT HEALTHY safe_mode=%s\n",
        safe_mode_latched ? "latched_until_restart" : "off");
  }

  delay(kLoopDelayMs);
}

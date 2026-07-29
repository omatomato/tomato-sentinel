#pragma once

#include <stddef.h>
#include <stdint.h>

#include "LocalDraft.h"
#include "OriginalCardputerDisplay.h"

namespace TomatoSentinelUiDetail {

constexpr uint16_t rgb565(uint8_t red, uint8_t green, uint8_t blue) {
  return static_cast<uint16_t>(((red & 0xF8) << 8) |
                               ((green & 0xFC) << 3) | (blue >> 3));
}

}  // namespace TomatoSentinelUiDetail

// Compact, allocation-free UI for the 240x135 original Cardputer display.
// Presentation is deliberately separate from input and policy behavior.
class TomatoSentinelUi final {
 public:
  enum class Tone : uint8_t {
    safe,
    muted,
    warning,
    danger,
  };

  TomatoSentinelUi(OriginalCardputerDisplay& display, const char* profile)
      : display_(display), profile_(profile) {}

  void drawReady() {
    beginFrame();
    drawCard(kSafe);

    label(20, 43, "DEVICE READY", kSafe);
    display_.setTextSize(2);
    display_.setTextColor(kText, kSurface);
    display_.setCursor(20, 57);
    display_.print("LOCAL CONSOLE");

    label(20, 82, "OFFLINE  /  RAM ONLY", kMuted);
    drawFooter(kDanger, "G0: CANCEL", kMuted, "TYPE TO START");
  }

  void drawDraft(const LocalDraft& draft, const char* status, Tone tone,
                 bool shift_armed) {
    beginFrame();
    drawCard(colorFor(tone));

    label(20, 42, "LOCAL DRAFT", kMuted);
    drawCounter(draft.length(), shift_armed);

    display_.fillRoundRect(16, 56, 208, 34, 5, kInput);
    display_.drawRoundRect(16, 56, 208, 34, 5, kDivider);
    display_.setTextSize(1);
    display_.setTextColor(kText, kInput);
    display_.setCursor(22, 64);
    display_.setTextWrap(true);
    if (draft.empty()) {
      display_.setTextColor(kMuted, kInput);
      display_.print("Draft empty");
    } else {
      display_.print(draft.text());
    }
    display_.setTextWrap(false);

    label(20, 94, status, colorFor(tone));
    drawFooter(kDanger, "G0: CLEAR", kWarning, "ENTER: DISCARD");
  }

  void drawSafeMode(uint8_t unfinished_boots) {
    beginFrame();
    drawCard(kWarning);
    drawStatusIcon(28, 58, kWarning, '!');

    label(48, 43, "FAIL-SAFE MODE", kWarning);
    display_.setTextSize(2);
    display_.setTextColor(kText, kSurface);
    display_.setCursor(48, 57);
    display_.print("RECOVERY");
    display_.setTextSize(1);
    display_.setTextColor(kMuted, kSurface);
    display_.setCursor(48, 81);
    display_.printf("UNFINISHED BOOTS  %u", unfinished_boots);

    drawFooter(kWarning, "LOCKED", kMuted, "G0+USB RECOVERY");
  }

  void drawCryptoInteropSelfTest() {
    beginFrame();
    drawCard(kSafe);
    drawStatusIcon(28, 58, kSafe, '+');

    label(48, 43, "CRYPTO VECTOR", kSafe);
    display_.setTextSize(2);
    display_.setTextColor(kText, kSurface);
    display_.setCursor(48, 57);
    display_.print("SELF-TEST PASS");
    label(48, 82, "NO PAIRING / NO STORAGE", kMuted);

    drawFooter(kDanger, "G0: CANCEL", kWarning, "COMPILE-ONLY");
  }

  void drawCancelled() {
    beginFrame();
    drawCard(kDanger);
    drawStatusIcon(28, 58, kDanger, 'X');

    label(48, 43, "CANCEL REQUESTED", kDanger);
    display_.setTextSize(2);
    display_.setTextColor(kText, kSurface);
    display_.setCursor(48, 57);
    display_.print("SAFE STATE");
    label(48, 82, "DRAFT CLEARED / NO JOB", kMuted);

    drawFooter(kDanger, "INPUT LOCKED", kMuted, "RESET TO CONTINUE");
  }

 private:
  static constexpr uint16_t kBackground =
      TomatoSentinelUiDetail::rgb565(6, 16, 20);
  static constexpr uint16_t kTopBar =
      TomatoSentinelUiDetail::rgb565(9, 25, 30);
  static constexpr uint16_t kSurface =
      TomatoSentinelUiDetail::rgb565(14, 34, 40);
  static constexpr uint16_t kInput =
      TomatoSentinelUiDetail::rgb565(8, 24, 29);
  static constexpr uint16_t kDivider =
      TomatoSentinelUiDetail::rgb565(38, 66, 72);
  static constexpr uint16_t kText =
      TomatoSentinelUiDetail::rgb565(238, 246, 243);
  static constexpr uint16_t kMuted =
      TomatoSentinelUiDetail::rgb565(133, 157, 153);
  static constexpr uint16_t kTomato =
      TomatoSentinelUiDetail::rgb565(238, 75, 61);
  static constexpr uint16_t kSafe =
      TomatoSentinelUiDetail::rgb565(55, 198, 126);
  static constexpr uint16_t kWarning =
      TomatoSentinelUiDetail::rgb565(247, 176, 65);
  static constexpr uint16_t kDanger =
      TomatoSentinelUiDetail::rgb565(255, 91, 82);
  static constexpr uint16_t kProfile =
      TomatoSentinelUiDetail::rgb565(22, 68, 52);

  void beginFrame() {
    display_.fillScreen(kBackground);
    drawTopBar();
  }

  void drawTopBar() {
    display_.fillRect(0, 0, display_.width(), 29, kTopBar);
    display_.drawFastHLine(0, 28, display_.width(), kDivider);

    display_.fillCircle(13, 14, 7, kTomato);
    display_.fillTriangle(9, 8, 13, 3, 14, 9, kSafe);
    display_.fillTriangle(13, 8, 18, 5, 16, 11, kSafe);

    display_.setTextSize(1);
    display_.setTextColor(kText, kTopBar);
    display_.setCursor(26, 7);
    display_.print("TOMATO");
    display_.setTextColor(kMuted, kTopBar);
    display_.setCursor(26, 17);
    display_.print("SENTINEL");

    display_.fillRoundRect(164, 7, 68, 15, 7, kProfile);
    display_.fillCircle(173, 14, 3, kSafe);
    display_.setTextColor(kText, kProfile);
    display_.setCursor(180, 11);
    display_.print(profile_);
  }

  void drawCard(uint16_t accent) {
    display_.fillRoundRect(8, 35, 224, 68, 8, kSurface);
    display_.drawRoundRect(8, 35, 224, 68, 8, kDivider);
    display_.fillRoundRect(8, 43, 4, 52, 2, accent);
  }

  void drawCounter(size_t length, bool shift_armed) {
    const uint16_t counter_color = shift_armed ? kWarning : kInput;
    display_.fillRoundRect(184, 40, 40, 14, 7, counter_color);
    display_.setTextSize(1);
    display_.setTextColor(shift_armed ? kBackground : kMuted, counter_color);
    display_.setCursor(190, 44);
    display_.printf("%u/64", length);
  }

  void drawStatusIcon(int32_t x, int32_t y, uint16_t color, char symbol) {
    display_.drawCircle(x, y, 11, kDivider);
    display_.fillCircle(x, y, 8, color);
    display_.setTextSize(1);
    display_.setTextColor(kBackground, color);
    display_.setCursor(x - 3, y - 3);
    display_.print(symbol);
  }

  void drawFooter(uint16_t left_color, const char* left_text,
                  uint16_t right_color, const char* right_text) {
    display_.fillRect(0, 108, display_.width(), 27, kTopBar);
    display_.drawFastHLine(0, 108, display_.width(), kDivider);

    display_.fillCircle(12, 121, 3, left_color);
    display_.setTextSize(1);
    display_.setTextColor(kText, kTopBar);
    display_.setCursor(20, 118);
    display_.print(left_text);

    display_.setTextColor(right_color, kTopBar);
    const int32_t text_width = display_.textWidth(right_text);
    display_.setCursor(display_.width() - text_width - 8, 118);
    display_.print(right_text);
  }

  void label(int32_t x, int32_t y, const char* text, uint16_t color) {
    display_.setTextSize(1);
    display_.setTextColor(color, kSurface);
    display_.setCursor(x, y);
    display_.print(text);
  }

  static constexpr uint16_t colorFor(Tone tone) {
    switch (tone) {
      case Tone::safe:
        return kSafe;
      case Tone::muted:
        return kMuted;
      case Tone::warning:
        return kWarning;
      case Tone::danger:
        return kDanger;
    }
    return kMuted;
  }

  OriginalCardputerDisplay& display_;
  const char* profile_;
};

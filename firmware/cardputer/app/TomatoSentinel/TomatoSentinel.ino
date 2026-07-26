#include <M5Unified.h>

#if !defined(TOMATO_TARGET_CARDPUTER_ORIGINAL) || \
    TOMATO_TARGET_CARDPUTER_ORIGINAL != 1
#error "Build refused: select the explicit original Cardputer target"
#endif

namespace {

constexpr char kFirmwareVersion[] = "0.1.0-poc";
constexpr char kBoardProfile[] = "board-profile:cardputer-original-v1";
constexpr char kOperatingProfile[] = "ASSISTANT";
constexpr uint32_t kLoopDelayMs = 10;

bool cancel_requested = false;

void drawHeader() {
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(8, 8);
  M5.Display.println("TOMATO SENTINEL");

  M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
  M5.Display.setCursor(8, 34);
  M5.Display.print("PROFILE: ");
  M5.Display.println(kOperatingProfile);
}

void drawReadyState() {
  drawHeader();
  M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(8, 68);
  M5.Display.println("BOARD: ORIGINAL");
  M5.Display.setCursor(8, 84);
  M5.Display.println("G0: CANCEL");
  M5.Display.setCursor(8, 108);
  M5.Display.println("READY / NO ACTIVE JOB");
}

void drawCancelState() {
  M5.Display.fillRect(0, 62, M5.Display.width(), 73, TFT_BLACK);
  drawHeader();
  M5.Display.setTextColor(TFT_ORANGE, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setCursor(8, 72);
  M5.Display.println("CANCEL REQUESTED");
  M5.Display.setCursor(8, 92);
  M5.Display.println("NO ACTIVE JOB");
  M5.Display.setCursor(8, 112);
  M5.Display.println("PROFILE REMAINS ASSISTANT");
}

[[noreturn]] void failUnsupportedBoard() {
  Serial.println("FATAL unsupported board; capabilities withheld");
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setTextColor(TFT_RED, TFT_BLACK);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(8, 8);
  M5.Display.println("START REFUSED");
  M5.Display.setTextSize(1);
  M5.Display.setCursor(8, 48);
  M5.Display.println("UNSUPPORTED BOARD");
  M5.Display.setCursor(8, 68);
  M5.Display.println("CAPABILITIES WITHHELD");

  while (true) {
    M5.update();
    delay(kLoopDelayMs);
  }
}

}  // namespace

void setup() {
  auto config = M5.config();
  config.serial_baudrate = 115200;
  config.clear_display = true;
  config.output_power = false;
  config.internal_imu = false;
  config.internal_rtc = false;
  config.internal_mic = false;
  config.internal_spk = false;
  config.external_imu = false;
  config.external_rtc = false;
  config.external_speaker_value = 0;
  config.external_display_value = 0;
  config.fallback_board = m5::board_t::board_unknown;

  M5.begin(config);

  if (M5.getBoard() != m5::board_t::board_M5Cardputer) {
    failUnsupportedBoard();
  }

  M5.Display.setRotation(1);
  M5.Display.fillScreen(TFT_BLACK);
  drawReadyState();

  Serial.printf(
      "READY firmware=%s board_profile=%s profile=%s\n",
      kFirmwareVersion,
      kBoardProfile,
      kOperatingProfile);
}

void loop() {
  // Physical cancellation is sampled before ordinary UI work.
  M5.update();
  if (M5.BtnA.wasPressed() && !cancel_requested) {
    cancel_requested = true;
    Serial.println("CANCEL REQUESTED status=no_active_job");
    drawCancelState();
  }

  delay(kLoopDelayMs);
}

#pragma once

#include <M5GFX.h>
#include <lgfx/v1/panel/Panel_ST7789.hpp>

// Exact, fixed wiring from the original 2023 M5Stack Cardputer schematic.
// This class deliberately uses LovyanGFX primitives instead of M5GFX automatic
// board detection, so startup neither probes unrelated pins nor caches a result
// in NVS.
class OriginalCardputerDisplay final : public lgfx::LGFX_Device {
 public:
  static constexpr int kMosiPin = 35;
  static constexpr int kSclkPin = 36;
  static constexpr int kDcPin = 34;
  static constexpr int kChipSelectPin = 37;
  static constexpr int kResetPin = 33;
  static constexpr int kBacklightPin = 38;

  OriginalCardputerDisplay() {
    auto bus_config = bus_.config();
    bus_config.spi_host = SPI3_HOST;
    bus_config.spi_mode = 0;
    bus_config.spi_3wire = true;
    bus_config.freq_write = 40000000;
    bus_config.freq_read = 16000000;
    bus_config.pin_mosi = kMosiPin;
    bus_config.pin_miso = -1;
    bus_config.pin_sclk = kSclkPin;
    bus_config.pin_dc = kDcPin;
    bus_.config(bus_config);
    panel_.setBus(&bus_);

    auto panel_config = panel_.config();
    panel_config.pin_cs = kChipSelectPin;
    panel_config.pin_rst = kResetPin;
    panel_config.pin_busy = -1;
    panel_config.panel_width = 135;
    panel_config.panel_height = 240;
    panel_config.offset_x = 52;
    panel_config.offset_y = 40;
    panel_config.readable = false;
    panel_config.invert = true;
    panel_.config(panel_config);

    auto light_config = backlight_.config();
    light_config.pin_bl = kBacklightPin;
    light_config.invert = false;
    light_config.freq = 256;
    light_config.pwm_channel = 7;
    backlight_.config(light_config);
    panel_.setLight(&backlight_);

    // Set the remembered brightness while no physical panel is attached.
    // init() will therefore keep PWM at zero through reset and bus startup.
    setBrightness(0);
    setPanel(&panel_);
  }

 private:
  lgfx::Panel_ST7789 panel_;
  lgfx::Bus_SPI bus_;
  lgfx::Light_PWM backlight_;
};

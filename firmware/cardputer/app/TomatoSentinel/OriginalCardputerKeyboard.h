#pragma once

#include <Arduino.h>

#include <stdint.h>

// Fixed wiring for the original 2023 Cardputer keyboard. The three selector
// pins only drive the address inputs of the onboard 74HC138. The seven sense
// pins are always inputs with pull-ups and are never driven by this class.
class OriginalCardputerKeyboard final {
 public:
  static constexpr uint8_t kSelectorPins[3] = {8, 9, 11};
  static constexpr uint8_t kSensePins[7] = {13, 15, 3, 4, 5, 6, 7};
  static constexpr uint32_t kDebounceMs = 30;
  static constexpr uint32_t kSelectorSettleUs = 5;

  enum class EventKind : uint8_t {
    none,
    character,
    backspace,
    enter,
    shift,
    ignored,
    ambiguous,
  };

  struct Event {
    EventKind kind;
    char character;
  };

  void begin(uint32_t now_ms) {
    // Load a low output value before changing direction to avoid a high pulse.
    for (const uint8_t pin : kSelectorPins) {
      digitalWrite(pin, LOW);
      pinMode(pin, OUTPUT);
    }
    for (const uint8_t pin : kSensePins) {
      pinMode(pin, INPUT_PULLUP);
    }

    selectRow(0);
    raw_mask_ = scanMask();
    stable_mask_ = raw_mask_;
    changed_at_ms_ = now_ms;
    initialized_ = true;
  }

  Event poll(uint32_t now_ms) {
    if (!initialized_) {
      return {EventKind::none, '\0'};
    }

    const uint64_t next_mask = scanMask();
    if (next_mask != raw_mask_) {
      raw_mask_ = next_mask;
      changed_at_ms_ = now_ms;
      return {EventKind::none, '\0'};
    }

    if (stable_mask_ == raw_mask_ ||
        now_ms - changed_at_ms_ < kDebounceMs) {
      return {EventKind::none, '\0'};
    }

    stable_mask_ = raw_mask_;
    if (stable_mask_ == 0) {
      return {EventKind::none, '\0'};
    }
    return decodeMask(stable_mask_);
  }

  static constexpr Event decodeMask(uint64_t mask) {
    if (mask == 0) {
      return {EventKind::none, '\0'};
    }

    uint8_t selected_index = 0;
    uint8_t selected_count = 0;
    for (uint8_t index = 0; index < 56; ++index) {
      if ((mask & (uint64_t{1} << index)) != 0) {
        selected_index = index;
        ++selected_count;
      }
    }

    if (selected_count != 1) {
      return {EventKind::ambiguous, '\0'};
    }

    const uint8_t selector = selected_index / 7;
    const uint8_t sense = selected_index % 7;
    const uint8_t row = 3 - (selector & 0x03);
    const uint8_t column =
        static_cast<uint8_t>(sense * 2 + (selector < 4 ? 1 : 0));
    if (row == 2 && column == 1) {
      return {EventKind::shift, '\0'};
    }
    const char value = kUnshiftedKeyMap[row][column];

    if (value == '\0' || value == '\t') {
      return {EventKind::ignored, '\0'};
    }
    if (value == '\b') {
      return {EventKind::backspace, '\0'};
    }
    if (value == '\n') {
      return {EventKind::enter, '\0'};
    }
    return {EventKind::character, value};
  }

  static constexpr char shiftedCharacter(char character) {
    if (character >= 'a' && character <= 'z') {
      return static_cast<char>(character - 'a' + 'A');
    }

    switch (character) {
      case '`':
        return '~';
      case '1':
        return '!';
      case '2':
        return '@';
      case '3':
        return '#';
      case '4':
        return '$';
      case '5':
        return '%';
      case '6':
        return '^';
      case '7':
        return '&';
      case '8':
        return '*';
      case '9':
        return '(';
      case '0':
        return ')';
      case '-':
        return '_';
      case '=':
        return '+';
      case '[':
        return '{';
      case ']':
        return '}';
      case '\\':
        return '|';
      case ';':
        return ':';
      case '\'':
        return '"';
      case ',':
        return '<';
      case '.':
        return '>';
      case '/':
        return '?';
      default:
        return character;
    }
  }

 private:
  static constexpr char kUnshiftedKeyMap[4][14] = {
      {'`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=',
       '\b'},
      {'\t', 'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']',
       '\\'},
      {'\0', '\0', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', '\'',
       '\n'},
      {'\0', '\0', '\0', 'z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/',
       ' '},
  };

  void selectRow(uint8_t selector) {
    for (uint8_t bit = 0; bit < 3; ++bit) {
      digitalWrite(kSelectorPins[bit],
                   (selector & (uint8_t{1} << bit)) != 0 ? HIGH : LOW);
    }
  }

  uint64_t scanMask() {
    uint64_t mask = 0;
    for (uint8_t selector = 0; selector < 8; ++selector) {
      selectRow(selector);
      delayMicroseconds(kSelectorSettleUs);
      for (uint8_t sense = 0; sense < 7; ++sense) {
        if (digitalRead(kSensePins[sense]) == LOW) {
          mask |= uint64_t{1} << (selector * 7 + sense);
        }
      }
    }
    selectRow(0);
    return mask;
  }

  uint64_t raw_mask_ = 0;
  uint64_t stable_mask_ = 0;
  uint32_t changed_at_ms_ = 0;
  bool initialized_ = false;
};

constexpr auto kOriginalKeyboardBacktick =
    OriginalCardputerKeyboard::decodeMask(uint64_t{1} << (7 * 7));
constexpr auto kOriginalKeyboardDigitOne =
    OriginalCardputerKeyboard::decodeMask(uint64_t{1} << (3 * 7));
constexpr auto kOriginalKeyboardSpace =
    OriginalCardputerKeyboard::decodeMask(uint64_t{1} << (0 * 7 + 6));
constexpr auto kOriginalKeyboardChord =
    OriginalCardputerKeyboard::decodeMask((uint64_t{1} << 0) |
                                         (uint64_t{1} << 1));
constexpr auto kOriginalKeyboardShift =
    OriginalCardputerKeyboard::decodeMask(uint64_t{1} << (1 * 7));

static_assert(kOriginalKeyboardBacktick.kind ==
              OriginalCardputerKeyboard::EventKind::character);
static_assert(kOriginalKeyboardBacktick.character == '`');
static_assert(kOriginalKeyboardDigitOne.character == '1');
static_assert(kOriginalKeyboardSpace.character == ' ');
static_assert(kOriginalKeyboardChord.kind ==
              OriginalCardputerKeyboard::EventKind::ambiguous);
static_assert(kOriginalKeyboardShift.kind ==
              OriginalCardputerKeyboard::EventKind::shift);
static_assert(OriginalCardputerKeyboard::shiftedCharacter('a') == 'A');
static_assert(OriginalCardputerKeyboard::shiftedCharacter('1') == '!');
static_assert(OriginalCardputerKeyboard::shiftedCharacter('/') == '?');

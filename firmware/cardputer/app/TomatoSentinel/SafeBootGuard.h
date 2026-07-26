#pragma once

#include <stdint.h>

// Flash-free crash-loop guard. State lives only in RTC memory so this proof of
// concept never mutates NVS, OTA metadata, partitions or eFuses at runtime.
class SafeBootGuard final {
 public:
  enum class ResetClass : uint8_t {
    clean_start,
    unfinished_start,
  };

  struct State {
    uint32_t magic;
    uint16_t version;
    uint8_t unfinished_boots;
    uint8_t boot_in_progress;
    uint32_t checksum;
  };

  struct Decision {
    State next;
    bool enter_safe_mode;
  };

  static constexpr uint32_t kMagic = 0x544F4D41;  // "TOMA"
  static constexpr uint16_t kVersion = 1;
  static constexpr uint8_t kSafeModeThreshold = 2;

  static constexpr uint32_t checksum(const State& state) {
    return state.magic ^ (static_cast<uint32_t>(state.version) << 16) ^
           (static_cast<uint32_t>(state.unfinished_boots) << 8) ^
           static_cast<uint32_t>(state.boot_in_progress) ^ 0xA55A3CC3;
  }

  static constexpr bool isValid(const State& state) {
    return state.magic == kMagic && state.version == kVersion &&
           state.boot_in_progress <= 1 && state.checksum == checksum(state);
  }

  static constexpr State cleanState() {
    State state{kMagic, kVersion, 0, 0, 0};
    state.checksum = checksum(state);
    return state;
  }

  static constexpr Decision begin(State previous, ResetClass reset_class) {
    if (!isValid(previous) || reset_class == ResetClass::clean_start) {
      previous = cleanState();
    } else if (previous.boot_in_progress != 0 &&
               previous.unfinished_boots < UINT8_MAX) {
      ++previous.unfinished_boots;
    }

    previous.boot_in_progress = 1;
    previous.checksum = checksum(previous);
    return {
        previous,
        previous.unfinished_boots >= kSafeModeThreshold,
    };
  }

  static constexpr State markHealthy(State state) {
    state = cleanState();
    return state;
  }
};

constexpr SafeBootGuard::State kEmptyBootGuardState{};
constexpr auto kFirstBoot =
    SafeBootGuard::begin(kEmptyBootGuardState,
                         SafeBootGuard::ResetClass::clean_start);
constexpr auto kFirstFailedBoot =
    SafeBootGuard::begin(kFirstBoot.next,
                         SafeBootGuard::ResetClass::unfinished_start);
constexpr auto kSecondFailedBoot =
    SafeBootGuard::begin(kFirstFailedBoot.next,
                         SafeBootGuard::ResetClass::unfinished_start);
constexpr auto kRecoveredBoot = SafeBootGuard::markHealthy(kSecondFailedBoot.next);

static_assert(SafeBootGuard::isValid(kFirstBoot.next));
static_assert(!kFirstBoot.enter_safe_mode);
static_assert(kFirstFailedBoot.next.unfinished_boots == 1);
static_assert(!kFirstFailedBoot.enter_safe_mode);
static_assert(kSecondFailedBoot.next.unfinished_boots == 2);
static_assert(kSecondFailedBoot.enter_safe_mode);
static_assert(SafeBootGuard::isValid(kRecoveredBoot));
static_assert(kRecoveredBoot.unfinished_boots == 0);
static_assert(kRecoveredBoot.boot_in_progress == 0);

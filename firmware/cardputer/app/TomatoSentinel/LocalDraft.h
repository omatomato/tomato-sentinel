#pragma once

#include <stddef.h>

// A bounded, RAM-only text buffer. It has no persistence or transport methods,
// so local keyboard input cannot accidentally become an executable command.
class LocalDraft final {
 public:
  static constexpr size_t kMaximumLength = 64;

  LocalDraft() { clear(); }

  bool append(char character) {
    if (length_ >= kMaximumLength) {
      return false;
    }

    text_[length_] = character;
    ++length_;
    text_[length_] = '\0';
    return true;
  }

  bool backspace() {
    if (length_ == 0) {
      return false;
    }

    --length_;
    text_[length_] = '\0';
    return true;
  }

  void clear() {
    // Volatile writes prevent the compiler from eliding the explicit erase.
    volatile char* cursor = text_;
    for (size_t index = 0; index < sizeof(text_); ++index) {
      cursor[index] = '\0';
    }
    length_ = 0;
  }

  const char* text() const { return text_; }
  size_t length() const { return length_; }
  bool empty() const { return length_ == 0; }

 private:
  char text_[kMaximumLength + 1]{};
  size_t length_ = 0;
};

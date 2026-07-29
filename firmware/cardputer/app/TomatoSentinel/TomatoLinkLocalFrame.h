#pragma once

#include <stddef.h>
#include <stdint.h>

// Allocation-free, transport-neutral framing for public local pairing
// messages. CRC-32 detects accidental corruption; it does not authenticate a
// peer and must never be treated as proof of device identity.
class TomatoLinkLocalFrame final {
 public:
  static constexpr size_t kHeaderSize = 20;
  static constexpr size_t kMaximumPayloadSize = 1024;
  static constexpr size_t kMaximumFrameSize =
      kHeaderSize + kMaximumPayloadSize;
  static constexpr uint8_t kVersion = 1;

  enum class Type : uint8_t {
    hello = 1,
    cancel = 2,
  };

  enum class Result : uint8_t {
    ok,
    need_more,
    invalid_argument,
    output_too_small,
    header_incomplete,
    magic_invalid,
    version_unsupported,
    type_unsupported,
    flags_invalid,
    sequence_invalid,
    reserved_invalid,
    payload_too_large,
    length_mismatch,
    hello_empty,
    cancel_payload_invalid,
    checksum_invalid,
    buffer_overflow,
    already_complete,
    cancelled,
  };

  struct View final {
    Type type;
    uint32_t sequence;
    const uint8_t* payload;
    size_t payload_length;
  };

  static Result encode(Type type, uint32_t sequence, const uint8_t* payload,
                       size_t payload_length, uint8_t* output,
                       size_t output_capacity, size_t* output_length);

  static Result decode(const uint8_t* encoded, size_t encoded_length,
                       View* view);

  class Decoder final {
   public:
    Decoder();
    ~Decoder();

    Result feed(const uint8_t* chunk, size_t chunk_length, View* view);
    void cancel();
    size_t bufferedBytes() const;

   private:
    uint8_t buffer_[kMaximumFrameSize];
    size_t buffered_;
    bool complete_;
    Result terminal_result_;

    Result reject(Result result);
    void clearBuffer();
  };

 private:
  struct Header final {
    Type type;
    uint32_t sequence;
    uint16_t payload_length;
    uint32_t checksum;
  };

  static Result inspectHeader(const uint8_t* encoded, size_t encoded_length,
                              Header* header);
  static Result validateShape(Type type, uint32_t sequence,
                              const uint8_t* payload, size_t payload_length);
  static uint32_t checksum(const uint8_t* header_without_crc,
                           const uint8_t* payload, size_t payload_length);
  static void secureClear(void* buffer, size_t length);
};

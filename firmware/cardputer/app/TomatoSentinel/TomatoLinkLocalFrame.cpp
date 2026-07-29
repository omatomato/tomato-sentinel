#include "TomatoLinkLocalFrame.h"

#include <string.h>

namespace {

constexpr uint8_t kMagic[4] = {'T', 'S', 'L', 'P'};
constexpr size_t kHeaderWithoutChecksumSize = 16;

uint16_t readBigEndian16(const uint8_t* input) {
  return static_cast<uint16_t>(static_cast<uint16_t>(input[0]) << 8) |
         input[1];
}

uint32_t readBigEndian32(const uint8_t* input) {
  return static_cast<uint32_t>(input[0]) << 24 |
         static_cast<uint32_t>(input[1]) << 16 |
         static_cast<uint32_t>(input[2]) << 8 |
         static_cast<uint32_t>(input[3]);
}

void writeBigEndian16(uint8_t* output, uint16_t value) {
  output[0] = static_cast<uint8_t>(value >> 8);
  output[1] = static_cast<uint8_t>(value);
}

void writeBigEndian32(uint8_t* output, uint32_t value) {
  output[0] = static_cast<uint8_t>(value >> 24);
  output[1] = static_cast<uint8_t>(value >> 16);
  output[2] = static_cast<uint8_t>(value >> 8);
  output[3] = static_cast<uint8_t>(value);
}

uint32_t updateCrc32(uint32_t crc, const uint8_t* input, size_t length) {
  for (size_t byte_index = 0; byte_index < length; ++byte_index) {
    crc ^= input[byte_index];
    for (uint8_t bit_index = 0; bit_index < 8; ++bit_index) {
      const uint32_t mask =
          0U - static_cast<uint32_t>(crc & static_cast<uint32_t>(1));
      crc = (crc >> 1) ^ (0xEDB88320U & mask);
    }
  }
  return crc;
}

}  // namespace

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::validateShape(
    Type type, uint32_t sequence, const uint8_t* payload,
    size_t payload_length) {
  if (type != Type::hello && type != Type::cancel) {
    return Result::type_unsupported;
  }
  if (sequence == 0) {
    return Result::sequence_invalid;
  }
  if (payload == nullptr && payload_length != 0) {
    return Result::invalid_argument;
  }
  if (payload_length > kMaximumPayloadSize) {
    return Result::payload_too_large;
  }
  if (type == Type::hello && payload_length == 0) {
    return Result::hello_empty;
  }
  if (type == Type::cancel && payload_length != 0) {
    return Result::cancel_payload_invalid;
  }
  return Result::ok;
}

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::encode(
    Type type, uint32_t sequence, const uint8_t* payload,
    size_t payload_length, uint8_t* output, size_t output_capacity,
    size_t* output_length) {
  if (output_length != nullptr) {
    *output_length = 0;
  }
  if (output == nullptr || output_length == nullptr) {
    return Result::invalid_argument;
  }
  const Result shape_result =
      validateShape(type, sequence, payload, payload_length);
  if (shape_result != Result::ok) {
    return shape_result;
  }
  const size_t required_size = kHeaderSize + payload_length;
  if (output_capacity < required_size) {
    return Result::output_too_small;
  }

  memcpy(output, kMagic, sizeof(kMagic));
  output[4] = kVersion;
  output[5] = static_cast<uint8_t>(type);
  writeBigEndian16(output + 6, 0);
  writeBigEndian32(output + 8, sequence);
  writeBigEndian16(output + 12, static_cast<uint16_t>(payload_length));
  writeBigEndian16(output + 14, 0);
  writeBigEndian32(output + 16, checksum(output, payload, payload_length));
  if (payload_length != 0) {
    memcpy(output + kHeaderSize, payload, payload_length);
  }
  *output_length = required_size;
  return Result::ok;
}

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::inspectHeader(
    const uint8_t* encoded, size_t encoded_length, Header* header) {
  if (encoded == nullptr || header == nullptr) {
    return Result::invalid_argument;
  }
  if (encoded_length < kHeaderSize) {
    return Result::header_incomplete;
  }
  if (memcmp(encoded, kMagic, sizeof(kMagic)) != 0) {
    return Result::magic_invalid;
  }
  if (encoded[4] != kVersion) {
    return Result::version_unsupported;
  }
  if (encoded[5] != static_cast<uint8_t>(Type::hello) &&
      encoded[5] != static_cast<uint8_t>(Type::cancel)) {
    return Result::type_unsupported;
  }
  if (readBigEndian16(encoded + 6) != 0) {
    return Result::flags_invalid;
  }
  const uint32_t sequence = readBigEndian32(encoded + 8);
  if (sequence == 0) {
    return Result::sequence_invalid;
  }
  const uint16_t payload_length = readBigEndian16(encoded + 12);
  if (payload_length > kMaximumPayloadSize) {
    return Result::payload_too_large;
  }
  if (readBigEndian16(encoded + 14) != 0) {
    return Result::reserved_invalid;
  }

  header->type = static_cast<Type>(encoded[5]);
  header->sequence = sequence;
  header->payload_length = payload_length;
  header->checksum = readBigEndian32(encoded + 16);
  return Result::ok;
}

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::decode(
    const uint8_t* encoded, size_t encoded_length, View* view) {
  if (view != nullptr) {
    *view = {Type::hello, 0, nullptr, 0};
  }
  if (encoded == nullptr || view == nullptr) {
    return Result::invalid_argument;
  }

  Header header{};
  const Result header_result =
      inspectHeader(encoded, encoded_length, &header);
  if (header_result != Result::ok) {
    return header_result;
  }
  if (encoded_length != kHeaderSize + header.payload_length) {
    return Result::length_mismatch;
  }
  const uint8_t* payload = encoded + kHeaderSize;
  const Result shape_result =
      validateShape(header.type, header.sequence, payload,
                    header.payload_length);
  if (shape_result != Result::ok) {
    return shape_result;
  }
  if (header.checksum != checksum(encoded, payload, header.payload_length)) {
    return Result::checksum_invalid;
  }

  *view = {header.type, header.sequence, payload, header.payload_length};
  return Result::ok;
}

uint32_t TomatoLinkLocalFrame::checksum(const uint8_t* header_without_crc,
                                        const uint8_t* payload,
                                        size_t payload_length) {
  uint32_t crc = updateCrc32(0xFFFFFFFFU, header_without_crc,
                             kHeaderWithoutChecksumSize);
  if (payload_length != 0) {
    crc = updateCrc32(crc, payload, payload_length);
  }
  return crc ^ 0xFFFFFFFFU;
}

TomatoLinkLocalFrame::Decoder::Decoder()
    : buffer_{},
      buffered_(0),
      complete_(false),
      terminal_result_(Result::ok) {}

TomatoLinkLocalFrame::Decoder::~Decoder() { clearBuffer(); }

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::Decoder::feed(
    const uint8_t* chunk, size_t chunk_length, View* view) {
  if (view != nullptr) {
    *view = {Type::hello, 0, nullptr, 0};
  }
  if (terminal_result_ != Result::ok) {
    return terminal_result_;
  }
  if (complete_) {
    return Result::already_complete;
  }
  if ((chunk == nullptr && chunk_length != 0) || view == nullptr) {
    return reject(Result::invalid_argument);
  }
  if (chunk_length > kMaximumFrameSize - buffered_) {
    return reject(Result::buffer_overflow);
  }
  if (chunk_length != 0) {
    memcpy(buffer_ + buffered_, chunk, chunk_length);
    buffered_ += chunk_length;
  }
  if (buffered_ < kHeaderSize) {
    return Result::need_more;
  }

  Header header{};
  const Result header_result = inspectHeader(buffer_, buffered_, &header);
  if (header_result != Result::ok) {
    return reject(header_result);
  }
  const size_t expected_length = kHeaderSize + header.payload_length;
  if (buffered_ < expected_length) {
    return Result::need_more;
  }
  if (buffered_ > expected_length) {
    return reject(Result::length_mismatch);
  }

  const Result decode_result = decode(buffer_, buffered_, view);
  if (decode_result != Result::ok) {
    return reject(decode_result);
  }
  complete_ = true;
  return Result::ok;
}

void TomatoLinkLocalFrame::Decoder::cancel() {
  if (!complete_ && terminal_result_ == Result::ok) {
    terminal_result_ = Result::cancelled;
  }
  clearBuffer();
}

size_t TomatoLinkLocalFrame::Decoder::bufferedBytes() const {
  return buffered_;
}

TomatoLinkLocalFrame::Result TomatoLinkLocalFrame::Decoder::reject(
    Result result) {
  terminal_result_ = result;
  clearBuffer();
  return result;
}

void TomatoLinkLocalFrame::Decoder::clearBuffer() {
  secureClear(buffer_, sizeof(buffer_));
  buffered_ = 0;
}

void TomatoLinkLocalFrame::secureClear(void* buffer, size_t length) {
  volatile uint8_t* cursor = static_cast<volatile uint8_t*>(buffer);
  while (cursor != nullptr && length-- != 0) {
    *cursor++ = 0;
  }
}

#if defined(TOMATO_LOCAL_FRAME_INTEROP_SELF_TEST) && \
    TOMATO_LOCAL_FRAME_INTEROP_SELF_TEST == 1

#include "TomatoLinkLocalFrameSelfTest.h"

#include <string.h>

#include "TomatoLinkLocalFrame.h"
#include "TomatoLinkLocalFrameInteropVector.h"

namespace {

namespace Vector = TomatoLinkLocalFrameInteropVector;

bool isCleared(const uint8_t* value, size_t length) {
  uint8_t aggregate = 0;
  for (size_t index = 0; index < length; ++index) {
    aggregate |= value[index];
  }
  return aggregate == 0;
}

}  // namespace

TomatoLinkLocalFrameSelfTestResult runTomatoLinkLocalFrameSelfTest() {
  uint8_t encoded[TomatoLinkLocalFrame::kMaximumFrameSize] = {};
  uint8_t corrupted[Vector::kEncodedLength] = {};
  size_t encoded_length = 0;
  TomatoLinkLocalFrame::View view{
      TomatoLinkLocalFrame::Type::hello, 0, nullptr, 0};
  TomatoLinkLocalFrameSelfTestResult result{false, "not_started"};

  do {
    if (TomatoLinkLocalFrame::encode(
            TomatoLinkLocalFrame::Type::hello, 1, Vector::kPayload,
            Vector::kPayloadLength, encoded, sizeof(encoded),
            &encoded_length) != TomatoLinkLocalFrame::Result::ok ||
        encoded_length != Vector::kEncodedLength ||
        memcmp(encoded, Vector::kEncoded, Vector::kEncodedLength) != 0) {
      result.status = "encode_mismatch";
      break;
    }

    if (TomatoLinkLocalFrame::decode(encoded, encoded_length, &view) !=
            TomatoLinkLocalFrame::Result::ok ||
        view.type != TomatoLinkLocalFrame::Type::hello ||
        view.sequence != 1 || view.payload_length != Vector::kPayloadLength ||
        memcmp(view.payload, Vector::kPayload, Vector::kPayloadLength) != 0) {
      result.status = "decode_mismatch";
      break;
    }

    {
      TomatoLinkLocalFrame::Decoder decoder;
      for (size_t index = 0; index < encoded_length; ++index) {
        const TomatoLinkLocalFrame::Result feed_result =
            decoder.feed(encoded + index, 1, &view);
        const TomatoLinkLocalFrame::Result expected =
            index + 1 == encoded_length
                ? TomatoLinkLocalFrame::Result::ok
                : TomatoLinkLocalFrame::Result::need_more;
        if (feed_result != expected) {
          result.status = "fragmentation_mismatch";
          break;
        }
      }
      if (strcmp(result.status, "fragmentation_mismatch") == 0) {
        break;
      }
      if (view.payload_length != Vector::kPayloadLength ||
          memcmp(view.payload, Vector::kPayload, Vector::kPayloadLength) !=
              0 ||
          decoder.feed(nullptr, 0, &view) !=
              TomatoLinkLocalFrame::Result::already_complete) {
        result.status = "decoder_completion_invalid";
        break;
      }
    }

    memcpy(corrupted, Vector::kEncoded, sizeof(corrupted));
    corrupted[16] ^= 0x01;
    if (TomatoLinkLocalFrame::decode(corrupted, sizeof(corrupted), &view) !=
        TomatoLinkLocalFrame::Result::checksum_invalid) {
      result.status = "checksum_not_rejected";
      break;
    }

    memcpy(corrupted, Vector::kEncoded, sizeof(corrupted));
    corrupted[12] = 0x04;
    corrupted[13] = 0x01;
    if (TomatoLinkLocalFrame::decode(corrupted, sizeof(corrupted), &view) !=
        TomatoLinkLocalFrame::Result::payload_too_large) {
      result.status = "oversize_not_rejected";
      break;
    }

    if (TomatoLinkLocalFrame::encode(
            TomatoLinkLocalFrame::Type::cancel, 1, Vector::kPayload,
            Vector::kPayloadLength, encoded, sizeof(encoded),
            &encoded_length) !=
        TomatoLinkLocalFrame::Result::cancel_payload_invalid) {
      result.status = "cancel_payload_not_rejected";
      break;
    }

    {
      TomatoLinkLocalFrame::Decoder overflow_decoder;
      if (overflow_decoder.feed(
              Vector::kEncoded, TomatoLinkLocalFrame::kMaximumFrameSize + 1,
              &view) != TomatoLinkLocalFrame::Result::buffer_overflow ||
          overflow_decoder.bufferedBytes() != 0) {
        result.status = "buffer_overflow_not_rejected";
        break;
      }
    }

    {
      TomatoLinkLocalFrame::Decoder cancelled_decoder;
      if (cancelled_decoder.feed(Vector::kEncoded, 8, &view) !=
          TomatoLinkLocalFrame::Result::need_more) {
        result.status = "cancel_setup_failed";
        break;
      }
      cancelled_decoder.cancel();
      if (cancelled_decoder.bufferedBytes() != 0 ||
          cancelled_decoder.feed(Vector::kEncoded + 8,
                                 Vector::kEncodedLength - 8, &view) !=
              TomatoLinkLocalFrame::Result::cancelled) {
        result.status = "cancel_not_terminal";
        break;
      }
    }

    result = {true, "pass"};
  } while (false);

  memset(corrupted, 0, sizeof(corrupted));
  memset(encoded, 0, sizeof(encoded));
  view = {TomatoLinkLocalFrame::Type::hello, 0, nullptr, 0};
  if (!isCleared(encoded, sizeof(encoded)) ||
      !isCleared(corrupted, sizeof(corrupted))) {
    return {false, "cleanup_failed"};
  }
  return result;
}

#endif

#if defined(TOMATO_CRYPTO_INTEROP_SELF_TEST) && \
    TOMATO_CRYPTO_INTEROP_SELF_TEST == 1

#include "TomatoLinkCryptoSelfTest.h"
#include <string.h>

#include "TomatoLinkCrypto.h"
#include "TomatoLinkCryptoInteropVector.h"

namespace {

namespace Vector = TomatoLinkCryptoInteropVector;

struct DeterministicRandomContext final {
  uint32_t state;
};

int deterministicPublicRandom(void* opaque_context, unsigned char* output,
                              size_t length) {
  if (opaque_context == nullptr || (output == nullptr && length != 0)) {
    return -1;
  }
  auto* context = static_cast<DeterministicRandomContext*>(opaque_context);
  for (size_t index = 0; index < length; ++index) {
    uint32_t value = context->state;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    context->state = value;
    output[index] = static_cast<uint8_t>(value);
  }
  return 0;
}

bool equals(const uint8_t* actual, const uint8_t* expected, size_t length) {
  return TomatoLinkCrypto::constantTimeEqual(actual, expected, length);
}

bool isCleared(const uint8_t* value, size_t length) {
  uint8_t aggregate = 0;
  for (size_t index = 0; index < length; ++index) {
    aggregate |= value[index];
  }
  return aggregate == 0;
}

}  // namespace

TomatoLinkCryptoSelfTestResult runTomatoLinkCryptoSelfTest() {
  uint8_t device_public[TomatoLinkCrypto::kKeySize] = {};
  uint8_t edge_public[TomatoLinkCrypto::kKeySize] = {};
  uint8_t device_shared[TomatoLinkCrypto::kKeySize] = {};
  uint8_t edge_shared[TomatoLinkCrypto::kKeySize] = {};
  uint8_t transcript_digest[TomatoLinkCrypto::kDigestSize] = {};
  uint8_t device_root[TomatoLinkCrypto::kKeySize] = {};
  uint8_t edge_root[TomatoLinkCrypto::kKeySize] = {};
  uint8_t rejected_output[TomatoLinkCrypto::kKeySize];
  uint8_t oversized_digest[TomatoLinkCrypto::kDigestSize];
  char fingerprint[TomatoLinkCrypto::kFingerprintTextSize] = {};
  DeterministicRandomContext random_context{0x544f4d41U};
  TomatoLinkCryptoSelfTestResult result{false, "not_started"};

  memset(rejected_output, 0xA5, sizeof(rejected_output));
  memset(oversized_digest, 0xA5, sizeof(oversized_digest));

  do {
    if (TomatoLinkCrypto::derivePublicKey(
            Vector::kDevicePrivate, device_public, deterministicPublicRandom,
            &random_context) != TomatoLinkCrypto::Result::ok ||
        !equals(device_public, Vector::kDevicePublic,
                sizeof(device_public))) {
      result.status = "device_public_mismatch";
      break;
    }

    if (TomatoLinkCrypto::derivePublicKey(
            Vector::kEdgePrivate, edge_public, deterministicPublicRandom,
            &random_context) != TomatoLinkCrypto::Result::ok ||
        !equals(edge_public, Vector::kEdgePublic, sizeof(edge_public))) {
      result.status = "edge_public_mismatch";
      break;
    }

    if (TomatoLinkCrypto::deriveSharedForInterop(
            Vector::kDevicePrivate, Vector::kEdgePublic, device_shared,
            deterministicPublicRandom, &random_context) !=
            TomatoLinkCrypto::Result::ok ||
        !equals(device_shared, Vector::kSharedSecret,
                sizeof(device_shared))) {
      result.status = "device_shared_mismatch";
      break;
    }

    if (TomatoLinkCrypto::deriveSharedForInterop(
            Vector::kEdgePrivate, Vector::kDevicePublic, edge_shared,
            deterministicPublicRandom, &random_context) !=
            TomatoLinkCrypto::Result::ok ||
        !equals(edge_shared, Vector::kSharedSecret, sizeof(edge_shared))) {
      result.status = "edge_shared_mismatch";
      break;
    }

    if (TomatoLinkCrypto::hashTranscript(
            reinterpret_cast<const uint8_t*>(Vector::kCanonicalTranscript),
            Vector::kCanonicalTranscriptLength, transcript_digest) !=
            TomatoLinkCrypto::Result::ok ||
        !equals(transcript_digest, Vector::kTranscriptDigest,
                sizeof(transcript_digest))) {
      result.status = "transcript_digest_mismatch";
      break;
    }

    if (TomatoLinkCrypto::formatFingerprint(transcript_digest, fingerprint) !=
            TomatoLinkCrypto::Result::ok ||
        strcmp(fingerprint, Vector::kFingerprint) != 0) {
      result.status = "fingerprint_mismatch";
      break;
    }

    if (TomatoLinkCrypto::deriveRoot(
            Vector::kDevicePrivate, Vector::kEdgePublic, transcript_digest,
            device_root, deterministicPublicRandom, &random_context) !=
            TomatoLinkCrypto::Result::ok ||
        !equals(device_root, Vector::kRoot, sizeof(device_root))) {
      result.status = "device_root_mismatch";
      break;
    }

    if (TomatoLinkCrypto::deriveRoot(
            Vector::kEdgePrivate, Vector::kDevicePublic, transcript_digest,
            edge_root, deterministicPublicRandom, &random_context) !=
            TomatoLinkCrypto::Result::ok ||
        !equals(edge_root, Vector::kRoot, sizeof(edge_root))) {
      result.status = "edge_root_mismatch";
      break;
    }

    if (TomatoLinkCrypto::deriveSharedForInterop(
            Vector::kDevicePrivate, Vector::kLowOrderPublic, rejected_output,
            deterministicPublicRandom, &random_context) !=
            TomatoLinkCrypto::Result::invalid_peer_key ||
        !isCleared(rejected_output, sizeof(rejected_output))) {
      result.status = "low_order_peer_not_rejected";
      break;
    }

    if (TomatoLinkCrypto::hashTranscript(
            reinterpret_cast<const uint8_t*>(Vector::kCanonicalTranscript),
            TomatoLinkCrypto::kMaxTranscriptSize + 1, oversized_digest) !=
            TomatoLinkCrypto::Result::transcript_too_large ||
        !isCleared(oversized_digest, sizeof(oversized_digest))) {
      result.status = "transcript_bound_not_enforced";
      break;
    }

    result = {true, "pass"};
  } while (false);

  TomatoLinkCrypto::secureClear(device_public, sizeof(device_public));
  TomatoLinkCrypto::secureClear(edge_public, sizeof(edge_public));
  TomatoLinkCrypto::secureClear(device_shared, sizeof(device_shared));
  TomatoLinkCrypto::secureClear(edge_shared, sizeof(edge_shared));
  TomatoLinkCrypto::secureClear(transcript_digest, sizeof(transcript_digest));
  TomatoLinkCrypto::secureClear(device_root, sizeof(device_root));
  TomatoLinkCrypto::secureClear(edge_root, sizeof(edge_root));
  TomatoLinkCrypto::secureClear(rejected_output, sizeof(rejected_output));
  TomatoLinkCrypto::secureClear(oversized_digest, sizeof(oversized_digest));
  TomatoLinkCrypto::secureClear(fingerprint, sizeof(fingerprint));
  TomatoLinkCrypto::secureClear(&random_context, sizeof(random_context));
  return result;
}

#endif

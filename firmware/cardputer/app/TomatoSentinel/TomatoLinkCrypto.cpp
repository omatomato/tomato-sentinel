#include "TomatoLinkCrypto.h"

#include <string.h>

#include <mbedtls/build_info.h>
#include <mbedtls/ecdh.h>
#include <mbedtls/ecp.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>

#if !defined(MBEDTLS_ECDH_C) || !defined(MBEDTLS_ECP_C) || \
    !defined(MBEDTLS_ECP_DP_CURVE25519_ENABLED)
#error "Tomato Link requires the pinned Mbed TLS Curve25519/ECDH support"
#endif

#if !defined(MBEDTLS_MD_C) || !defined(MBEDTLS_SHA256_C)
#error "Tomato Link requires the pinned Mbed TLS MD/SHA-256 support"
#endif

namespace {

constexpr uint8_t kHkdfInfo[] =
    "tomato-sentinel/tomato-link/ephemeral-root/v1";
constexpr size_t kHkdfInfoLength = sizeof(kHkdfInfo) - 1;
constexpr size_t kHkdfExpandInputSize = kHkdfInfoLength + 1;

bool isAllZero(const uint8_t* value, size_t length) {
  uint8_t aggregate = 0;
  for (size_t index = 0; index < length; ++index) {
    aggregate |= value[index];
  }
  return aggregate == 0;
}

}  // namespace

TomatoLinkCrypto::Result TomatoLinkCrypto::derivePublicKey(
    const uint8_t private_key[kKeySize], uint8_t public_key[kKeySize],
    RandomCallback random_callback, void* random_context) {
  if (public_key != nullptr) {
    secureClear(public_key, kKeySize);
  }
  if (private_key == nullptr || public_key == nullptr ||
      random_callback == nullptr) {
    return Result::invalid_argument;
  }

  mbedtls_ecp_keypair keypair;
  mbedtls_ecp_keypair_init(&keypair);
  Result result = Result::crypto_failure;
  size_t output_length = 0;

  if (mbedtls_ecp_read_key(MBEDTLS_ECP_DP_CURVE25519, &keypair, private_key,
                           kKeySize) != 0) {
    goto cleanup;
  }
  if (mbedtls_ecp_mul(&keypair.MBEDTLS_PRIVATE(grp),
                      &keypair.MBEDTLS_PRIVATE(Q),
                      &keypair.MBEDTLS_PRIVATE(d),
                      &keypair.MBEDTLS_PRIVATE(grp).G, random_callback,
                      random_context) != 0) {
    goto cleanup;
  }

  if (mbedtls_ecp_point_write_binary(
          &keypair.MBEDTLS_PRIVATE(grp), &keypair.MBEDTLS_PRIVATE(Q),
          MBEDTLS_ECP_PF_UNCOMPRESSED, &output_length, public_key,
          kKeySize) != 0 ||
      output_length != kKeySize) {
    goto cleanup;
  }

  result = Result::ok;

cleanup:
  mbedtls_ecp_keypair_free(&keypair);
  if (result != Result::ok) {
    secureClear(public_key, kKeySize);
  }
  return result;
}

TomatoLinkCrypto::Result TomatoLinkCrypto::computeShared(
    const uint8_t private_key[kKeySize],
    const uint8_t peer_public_key[kKeySize],
    uint8_t shared_secret[kKeySize], RandomCallback random_callback,
    void* random_context) {
  if (shared_secret != nullptr) {
    secureClear(shared_secret, kKeySize);
  }
  if (private_key == nullptr || peer_public_key == nullptr ||
      shared_secret == nullptr || random_callback == nullptr) {
    return Result::invalid_argument;
  }

  mbedtls_ecp_keypair own_key;
  mbedtls_ecp_point peer_point;
  mbedtls_mpi shared;
  mbedtls_ecp_keypair_init(&own_key);
  mbedtls_ecp_point_init(&peer_point);
  mbedtls_mpi_init(&shared);
  Result result = Result::crypto_failure;

  if (mbedtls_ecp_read_key(MBEDTLS_ECP_DP_CURVE25519, &own_key, private_key,
                           kKeySize) != 0) {
    goto cleanup;
  }
  if (mbedtls_ecp_point_read_binary(&own_key.MBEDTLS_PRIVATE(grp),
                                    &peer_point, peer_public_key,
                                    kKeySize) != 0 ||
      mbedtls_ecp_check_pubkey(&own_key.MBEDTLS_PRIVATE(grp), &peer_point) !=
          0) {
    result = Result::invalid_peer_key;
    goto cleanup;
  }
  if (mbedtls_ecdh_compute_shared(
          &own_key.MBEDTLS_PRIVATE(grp), &shared, &peer_point,
          &own_key.MBEDTLS_PRIVATE(d), random_callback, random_context) != 0) {
    result = Result::crypto_failure;
    goto cleanup;
  }
  if (mbedtls_mpi_write_binary_le(&shared, shared_secret, kKeySize) != 0 ||
      isAllZero(shared_secret, kKeySize)) {
    result = Result::invalid_peer_key;
    goto cleanup;
  }

  result = Result::ok;

cleanup:
  mbedtls_mpi_free(&shared);
  mbedtls_ecp_point_free(&peer_point);
  mbedtls_ecp_keypair_free(&own_key);
  if (result != Result::ok) {
    secureClear(shared_secret, kKeySize);
  }
  return result;
}

TomatoLinkCrypto::Result TomatoLinkCrypto::deriveRoot(
    const uint8_t private_key[kKeySize],
    const uint8_t peer_public_key[kKeySize],
    const uint8_t transcript_digest[kDigestSize], uint8_t root[kKeySize],
    RandomCallback random_callback, void* random_context) {
  if (root != nullptr) {
    secureClear(root, kKeySize);
  }
  if (private_key == nullptr || peer_public_key == nullptr ||
      transcript_digest == nullptr || root == nullptr ||
      random_callback == nullptr) {
    return Result::invalid_argument;
  }

  uint8_t shared_secret[kKeySize] = {};
  const Result shared_result =
      computeShared(private_key, peer_public_key, shared_secret,
                    random_callback, random_context);
  if (shared_result != Result::ok) {
    secureClear(shared_secret, sizeof(shared_secret));
    return shared_result;
  }

  const Result hkdf_result =
      hkdfSha256(shared_secret, transcript_digest, kHkdfInfo,
                 kHkdfInfoLength, root);
  secureClear(shared_secret, sizeof(shared_secret));
  if (hkdf_result != Result::ok) {
    secureClear(root, kKeySize);
  }
  return hkdf_result;
}

TomatoLinkCrypto::Result TomatoLinkCrypto::hashTranscript(
    const uint8_t* transcript, size_t transcript_length,
    uint8_t digest[kDigestSize]) {
  if (digest != nullptr) {
    secureClear(digest, kDigestSize);
  }
  if (transcript == nullptr || digest == nullptr || transcript_length == 0) {
    return Result::invalid_argument;
  }
  if (transcript_length > kMaxTranscriptSize) {
    return Result::transcript_too_large;
  }
  if (mbedtls_sha256(transcript, transcript_length, digest, 0) != 0) {
    secureClear(digest, kDigestSize);
    return Result::crypto_failure;
  }
  return Result::ok;
}

TomatoLinkCrypto::Result TomatoLinkCrypto::formatFingerprint(
    const uint8_t digest[kDigestSize],
    char fingerprint[kFingerprintTextSize]) {
  if (fingerprint != nullptr) {
    secureClear(fingerprint, kFingerprintTextSize);
  }
  if (digest == nullptr || fingerprint == nullptr) {
    return Result::invalid_argument;
  }

  constexpr char kHex[] = "0123456789abcdef";
  size_t output_index = 0;
  for (size_t byte_index = 0; byte_index < kFingerprintBytes; ++byte_index) {
    if (byte_index != 0 && byte_index % 2 == 0) {
      fingerprint[output_index++] = '-';
    }
    fingerprint[output_index++] = kHex[digest[byte_index] >> 4];
    fingerprint[output_index++] = kHex[digest[byte_index] & 0x0F];
  }
  fingerprint[output_index] = '\0';
  return output_index + 1 == kFingerprintTextSize ? Result::ok
                                                  : Result::crypto_failure;
}

TomatoLinkCrypto::Result TomatoLinkCrypto::hkdfSha256(
    const uint8_t input_key[kKeySize], const uint8_t salt[kDigestSize],
    const uint8_t* info, size_t info_length, uint8_t output[kKeySize]) {
  if (output != nullptr) {
    secureClear(output, kKeySize);
  }
  if (input_key == nullptr || salt == nullptr || info == nullptr ||
      output == nullptr || info_length == 0 ||
      info_length + 1 > kHkdfExpandInputSize) {
    return Result::invalid_argument;
  }

  const mbedtls_md_info_t* sha256 =
      mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (sha256 == nullptr) {
    return Result::crypto_failure;
  }

  uint8_t pseudorandom_key[kDigestSize] = {};
  uint8_t expand_input[kHkdfExpandInputSize] = {};
  Result result = Result::crypto_failure;

  if (mbedtls_md_hmac(sha256, salt, kDigestSize, input_key, kKeySize,
                      pseudorandom_key) != 0) {
    goto cleanup;
  }

  memcpy(expand_input, info, info_length);
  expand_input[info_length] = 0x01;
  if (mbedtls_md_hmac(sha256, pseudorandom_key, kDigestSize, expand_input,
                      info_length + 1, output) != 0) {
    goto cleanup;
  }

  result = Result::ok;

cleanup:
  secureClear(expand_input, sizeof(expand_input));
  secureClear(pseudorandom_key, sizeof(pseudorandom_key));
  if (result != Result::ok) {
    secureClear(output, kKeySize);
  }
  return result;
}

bool TomatoLinkCrypto::constantTimeEqual(const uint8_t* left,
                                         const uint8_t* right,
                                         size_t length) {
  if ((left == nullptr || right == nullptr) && length != 0) {
    return false;
  }
  uint8_t difference = 0;
  for (size_t index = 0; index < length; ++index) {
    difference |= left[index] ^ right[index];
  }
  return difference == 0;
}

void TomatoLinkCrypto::secureClear(void* buffer, size_t length) {
  volatile uint8_t* cursor = static_cast<volatile uint8_t*>(buffer);
  while (cursor != nullptr && length-- != 0) {
    *cursor++ = 0;
  }
}

#if defined(TOMATO_CRYPTO_INTEROP_SELF_TEST) && \
    TOMATO_CRYPTO_INTEROP_SELF_TEST == 1
TomatoLinkCrypto::Result TomatoLinkCrypto::deriveSharedForInterop(
    const uint8_t private_key[kKeySize],
    const uint8_t peer_public_key[kKeySize],
    uint8_t shared_secret[kKeySize], RandomCallback random_callback,
    void* random_context) {
  return computeShared(private_key, peer_public_key, shared_secret,
                       random_callback, random_context);
}
#endif

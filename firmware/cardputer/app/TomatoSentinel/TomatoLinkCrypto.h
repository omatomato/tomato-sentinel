#pragma once

#include <stddef.h>
#include <stdint.h>

// Allocation-free cryptographic primitives for the Tomato Link pairing
// transcript. This class does not generate, persist, provision or transport
// keys. Callers must provide a reviewed RNG callback for X25519 blinding.
class TomatoLinkCrypto final {
 public:
  static constexpr size_t kKeySize = 32;
  static constexpr size_t kDigestSize = 32;
  static constexpr size_t kFingerprintBytes = 16;
  static constexpr size_t kFingerprintTextSize = 40;
  static constexpr size_t kMaxTranscriptSize = 2048;

  using RandomCallback = int (*)(void* context, unsigned char* output,
                                 size_t length);

  enum class Result : uint8_t {
    ok,
    invalid_argument,
    transcript_too_large,
    invalid_peer_key,
    crypto_failure,
  };

  static Result derivePublicKey(const uint8_t private_key[kKeySize],
                                uint8_t public_key[kKeySize],
                                RandomCallback random_callback,
                                void* random_context);

  static Result deriveRoot(const uint8_t private_key[kKeySize],
                           const uint8_t peer_public_key[kKeySize],
                           const uint8_t transcript_digest[kDigestSize],
                           uint8_t root[kKeySize],
                           RandomCallback random_callback,
                           void* random_context);

  static Result hashTranscript(const uint8_t* transcript,
                               size_t transcript_length,
                               uint8_t digest[kDigestSize]);

  static Result formatFingerprint(
      const uint8_t digest[kDigestSize],
      char fingerprint[kFingerprintTextSize]);

  static bool constantTimeEqual(const uint8_t* left, const uint8_t* right,
                                size_t length);
  static void secureClear(void* buffer, size_t length);

#if defined(TOMATO_CRYPTO_INTEROP_SELF_TEST) && \
    TOMATO_CRYPTO_INTEROP_SELF_TEST == 1
  // Exposed only in the compile-only interoperability image so the published
  // RFC 7748 shared-secret vector can be verified independently of HKDF.
  static Result deriveSharedForInterop(
      const uint8_t private_key[kKeySize],
      const uint8_t peer_public_key[kKeySize],
      uint8_t shared_secret[kKeySize], RandomCallback random_callback,
      void* random_context);
#endif

 private:
  static Result computeShared(const uint8_t private_key[kKeySize],
                              const uint8_t peer_public_key[kKeySize],
                              uint8_t shared_secret[kKeySize],
                              RandomCallback random_callback,
                              void* random_context);

  static Result hkdfSha256(const uint8_t input_key[kKeySize],
                           const uint8_t salt[kDigestSize],
                           const uint8_t* info, size_t info_length,
                           uint8_t output[kKeySize]);
};

#pragma once

#if !defined(TOMATO_CRYPTO_INTEROP_SELF_TEST) || \
    TOMATO_CRYPTO_INTEROP_SELF_TEST != 1
#error "Crypto interoperability self-test is forbidden in ordinary firmware"
#endif

struct TomatoLinkCryptoSelfTestResult final {
  bool passed;
  const char* status;
};

TomatoLinkCryptoSelfTestResult runTomatoLinkCryptoSelfTest();

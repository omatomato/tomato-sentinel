#pragma once

#if !defined(TOMATO_LOCAL_FRAME_INTEROP_SELF_TEST) || \
    TOMATO_LOCAL_FRAME_INTEROP_SELF_TEST != 1
#error "Local pairing frame self-test is forbidden in ordinary firmware"
#endif

struct TomatoLinkLocalFrameSelfTestResult final {
  bool passed;
  const char* status;
};

TomatoLinkLocalFrameSelfTestResult runTomatoLinkLocalFrameSelfTest();

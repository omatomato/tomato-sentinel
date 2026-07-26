# Cardputer firmware guidance

- Every hardware revision uses an explicit board profile.
- Never infer a capability from an untrusted message.
- Keep pins and driver choices out of generic application logic.
- Audio buffers, transport messages and retries must be bounded.
- Recording and active profiles require visible indicators.
- Physical cancellation has priority over ordinary UI work.
- Simulator results are not evidence of physical hardware behavior.
- Do not add an Arduino, ESP-IDF or PlatformIO dependency until it is pinned,
  cataloged, licensed and approved by ADR.

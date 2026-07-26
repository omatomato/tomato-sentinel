# Device protocol guidance

- Treat every envelope and payload as untrusted external input.
- Authenticate before mutating replay state.
- Keep canonical serialization deterministic and bounded.
- Use per-device credentials; never a global device secret.
- Do not expose authentication keys through models, results or errors.
- Capability reports must match provisioned trusted board profiles exactly.
- Simulation cryptography must be labeled as simulation, not production trust.
- Physical cancellation has a fixed payload and cannot dispatch arbitrary
  operations.

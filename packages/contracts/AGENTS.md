# Contract guidance

This subtree owns language-neutral schemas shared across Tomato Sentinel.

- Use JSON Schema Draft 2020-12 unless an accepted ADR changes the format.
- Give every schema a stable HTTPS `$id` and explicit `contract_version`.
- Reject unknown fields at external trust boundaries.
- Keep secrets out of examples and fixtures.
- Add positive and negative validation tests for every schema change.
- Compatibility-breaking changes require a new schema version and migration
  documentation.
- Generated language bindings are derived artifacts, not the source of truth.

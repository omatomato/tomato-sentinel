# Policy engine guidance

This subtree implements deterministic authorization. Read the repository root
`AGENTS.md` and `docs/security/authorization-model.md` first.

## Rules

- Deny by default.
- Keep evaluation independent of wall-clock and network access; pass time and
  verified context as inputs.
- Use exact, canonical typed identifiers. Do not authorize by substring.
- Return stable reason codes suitable for audit and tests.
- Confirmation approves one exact plan and cannot create authorization.
- R3 manifests must be rejected by the registry.
- The registry is explicit and versioned; no dynamic imports or hidden tools.
- Tests must cover every allow path and relevant denial branch.
- Do not add framework, database or provider dependencies to domain logic.

# ADR-0002: Select the initial language toolchain and contract format

- Status: Accepted
- Date: 2026-07-25

## Context

The simulated MVP needs a deterministic policy engine, versioned contracts,
fake adapters and tests before hardware integration. The wider product will
also need a browser operator console and Cardputer firmware.

Using one language everywhere would weaken at least one execution placement:
Python has the strongest fit for orchestration, AI and vision; TypeScript fits
the operator console; C++ is required by the Cardputer ecosystem. Shared
authorization must remain server-side rather than being reimplemented in each
language.

## Decision

### Languages

- Python 3.13 and 3.14 are supported for backend packages and tests.
- Python 3.13 is the local default until the development image includes 3.14.
- TypeScript will be introduced with the first operator-console artifact.
- C++ will be introduced with the first Cardputer firmware artifact.

Python services use type hints, immutable domain values where practical,
runtime validation at trust boundaries and no global mutable policy state.

### Python project management

Use uv with:

- `pyproject.toml` as project and tool configuration;
- a committed cross-platform `uv.lock`;
- exact CI synchronization with `uv sync --locked`;
- explicit dependency updates followed by review and lock regeneration;
- no floating Git dependencies.

The root is initially a non-package Python workspace. Deployable packages gain
their own build metadata when they have a release artifact.

### Quality tools

- Ruff for formatting and linting;
- mypy in strict mode for static type checking;
- pytest for tests;
- `jsonschema` for validating language-neutral contract schemas and structured
  input at Python trust boundaries.

The quality tools are development dependencies. `jsonschema` is a runtime
dependency because the orchestrator rejects external structured input against
the source contracts before constructing domain values. All dependencies are
pinned through the lockfile and registered in the upstream catalog.

### Contracts

JSON Schema Draft 2020-12 is the initial language-neutral source of truth for:

- commands;
- tool manifests;
- policy requests and decisions;
- events and audit envelopes.

Schemas:

- have stable `$id` values;
- include an explicit contract version;
- reject unknown fields at trust boundaries;
- use typed identifiers rather than unqualified strings where practical;
- include positive and negative examples in tests;
- are never generated directly from an LLM response at execution time.

Language-specific models implement the schemas but do not replace them.

### CI

GitHub Actions runs on Python 3.13 and 3.14 with read-only repository
permissions. Third-party actions are pinned to exact commit SHAs. CI performs:

1. locked dependency synchronization;
2. formatting check;
3. lint;
4. strict type checking;
5. tests;
6. schema validation.

## Alternatives considered

### TypeScript for all backend code

Rejected for the initial backend because speech, vision and AI provider
integration will otherwise require additional runtime boundaries. TypeScript
remains appropriate for the operator console.

### Python for the operator console

Rejected because it would not eliminate browser-side TypeScript and would
encourage UI-specific authorization logic.

### Protobuf as the first contract format

Deferred. Protobuf is valuable for compact device transport, but JSON Schema is
easier to inspect during the policy and MVP foundation. A later device-protocol
ADR may introduce Protobuf or CBOR while mapping to the same domain contracts.

### OpenAPI as the source of all contracts

Rejected. OpenAPI is appropriate for HTTP transport but should not own internal
events, device messages or policy-domain semantics.

## Consequences

- The backend foundation can be developed and tested with the installed Python
  3.13 runtime.
- CI verifies compatibility with the current Python 3.14 stable series.
- The project intentionally becomes polyglot only when each execution
  placement needs it.
- Contract compatibility and code generation policy need a later ADR before
  public APIs or firmware transport stabilize.
- Tooling itself is an upstream supply-chain dependency and must remain pinned,
  cataloged and reviewable.

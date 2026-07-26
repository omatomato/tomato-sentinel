# Development workflow

## Current phase

The repository is in the simulated vertical-slice phase. Python and its initial
quality toolchain are approved by ADR-0002. Application frameworks are not yet
approved. Do not introduce a framework incidentally while editing domain logic,
documentation or contracts.

## Change preparation

For every change, record:

- bounded objective;
- affected components and trust boundaries;
- data classes;
- risk class and interaction mode, if executable;
- required authorization and confirmation;
- positive tests and negative controls;
- upstream dependencies and network destinations.

## Validation

Documentation changes require:

- Markdown link validation;
- duplicate-heading and malformed-heading checks;
- YAML parsing where YAML changes;
- secret-pattern review;
- final diff review.

Implementation changes additionally require the repository-provided formatter,
linter, type checker, unit tests, relevant integration tests and security
regressions.

External APIs and hardware are replaced by fakes in ordinary tests.

Current Python checks:

```text
uv sync --locked --all-groups
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

## Applicability

Definition-of-done controls apply according to behavior:

- an instantaneous R0 query may mark cancellation as not applicable;
- a backend-only change may mark hardware capability checks as not applicable;
- long-running work cannot mark timeout, cancellation or idempotency as not
  applicable;
- sensitive actions cannot mark denial tests or audit as not applicable.

State why a control is not applicable.

## Repository hygiene

- Keep generated files distinguishable from hand-written domain logic.
- Do not commit local credentials, evidence, captures or environment files.
- Preserve unrelated worktree changes.
- Pin production dependencies.
- Record commands actually executed.
- Never claim tests passed when they were skipped or unavailable.

## Foundation checklist

- repository governance and documentation;
- license decision before public release;
- supported language and toolchain ADR;
- CI with formatting, lint, type checking and tests;
- secret and dependency scanning;
- SBOM generation;
- contracts and schema compatibility policy;
- fake Cardputer, camera, speech and notification adapters;
- deterministic policy engine and denial tests;
- signed-build and device-trust design.

# ADR-0001: Establish foundation boundaries before implementation

- Status: Accepted
- Date: 2026-07-25

## Context

The initial project specification combined product vision, architecture,
security rules, privacy expectations, upstream governance, coding conventions
and agent workflow in one large file. The repository did not yet contain
software or automated validation.

Several concepts needed disambiguation before implementation:

- operator role versus device profile;
- normal resource authorization versus laboratory operation scope;
- `allow_with_confirmation` versus `allow` plus a hidden confirmation flag;
- whether R3 could be manually executable;
- the missing edge runtime;
- firmware signing placed too late in the roadmap.

## Decision

1. Keep a concise repository-wide `AGENTS.md` and focused normative documents.
2. Preserve the complete original specification as a historical snapshot.
3. Use distinct role, profile, resource grant, operation scope, capability,
   risk, confirmation and obligation concepts.
4. Represent confirmation through `allow_with_confirmation`.
5. Make R3 non-executable, non-registrable and non-proposable.
6. Add an explicit edge-agent placement.
7. Treat device trust, signed firmware and rollback protection as foundation
   work before laboratory capabilities.
8. Validate a simulated vertical slice before physical hardware integration.

## Consequences

- Foundational contracts and policy receive priority over feature breadth.
- Documentation becomes easier to load and review by subsystem.
- Camera monitoring can use ordinary resource grants without misusing a
  cybersecurity scope.
- Active tools cannot be implemented before their controls and denial tests.
- The snapshot remains normative for requirements not yet migrated. Current
  focused documents and later accepted ADRs take precedence where they
  intentionally clarify or replace its wording.

## Follow-up

- select language/toolchain versions in a separate ADR;
- define the language-neutral contract format;
- design device provisioning and signed-update trust;
- add automated documentation validation;
- build the simulated MVP.

# Contributing

Tomato Sentinel is currently private and in its foundation phase.

Before contributing:

1. read `AGENTS.md`;
2. read the documentation for the affected subsystem;
3. identify trust boundaries, data classes and authorization impact;
4. keep the change small and reviewable;
5. add positive tests and relevant denial tests with executable behavior.

Do not commit credentials, private camera addresses, raw personal data,
production captures or unreviewed upstream code.

## Commit style

Use concise imperative commits with an optional conventional prefix:

```text
docs: define device trust states
feat(policy): validate canonical CIDR scope
test(camera): deny cross-tenant monitoring
```

## Pull requests

A pull request should explain:

- the problem and bounded objective;
- affected trust boundaries;
- risk class, when applicable;
- authorization and confirmation behavior;
- tests and negative controls;
- commands actually run;
- checks not run and why;
- upstream origin and license, when applicable.

No sensitive feature is accepted without a denial test.

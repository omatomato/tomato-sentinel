# Tomato Sentinel

Tomato Sentinel is a privacy-conscious AI, automation, physical-monitoring,
asset-visibility and authorized cybersecurity platform built around M5Stack
Cardputer devices, edge nodes and backend services.

The Cardputer is a portable interface and field terminal. It captures bounded
push-to-talk audio, accepts keyboard input, displays alerts, exposes verified
hardware capabilities and provides physical confirmation. Expensive speech,
language-model and computer-vision processing runs on authorized edge or
backend infrastructure.

## Status

Tomato Sentinel is in its foundation phase. The repository defines the product
boundaries, architecture, authorization model, risk policy, privacy baseline
and upstream-software governance. It also contains the first side-effect-free
policy-engine core and JSON Schema contracts. No security tool, camera worker
or production service is implemented yet.

## Core principle

> AI may propose registered operations. Deterministic code decides whether an
> operation is allowed.

Natural-language output is never executed directly.

## Documentation

- [Product vision](docs/product/vision.md)
- [First MVP](docs/product/mvp.md)
- [System architecture](docs/architecture/system-architecture.md)
- [Authorization model](docs/security/authorization-model.md)
- [Tool risk model](docs/security/tool-risk-model.md)
- [Privacy and data governance](docs/privacy/data-governance.md)
- [Upstream-software policy](docs/governance/upstream-software.md)
- [Development workflow](docs/operations/development-workflow.md)
- [Language and toolchain decision](docs/decisions/ADR-0002-language-toolchain-and-contracts.md)
- [Original specification snapshot](docs/product/product-specification-original.md)

Repository-wide agent and contributor constraints are in [AGENTS.md](AGENTS.md).

## Planned repository layout

```text
firmware/cardputer/       Cardputer firmware and board profiles
apps/api/                 public/control API
apps/operator-console/    operator interface
apps/mobile/              mobile client
apps/edge-agent/          local discovery, camera and hardware edge runtime
services/                 bounded backend services
packages/contracts/       shared commands, events and schemas
packages/policy-engine/   deterministic authorization
packages/scope/           canonical scopes and resource grants
integrations/             isolated external adapters
config/                   reviewed declarative configuration
infra/                    deployment, provisioning and observability
tests/                    integration, end-to-end, security and simulation
```

Directories will be introduced with their first owned artifact rather than as
empty placeholders.

## Development

The initial backend workspace supports Python 3.13 and 3.14 and uses uv
`0.11.29`.

```text
uv sync --locked --all-groups
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

Dependencies and CI actions are pinned and registered in
`config/upstream/software-catalog.yaml`. The current Python development SBOM is
stored in `sbom/python-development.cdx.json`.

## Security

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

## License

No open-source license has been selected. The repository is private and no
permission to copy, redistribute or reuse its contents is granted at this
stage. Upstream projects retain their own licenses.

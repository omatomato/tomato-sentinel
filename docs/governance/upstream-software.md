# Upstream-software governance

## Objective

Open-source availability is not approval. Every upstream project is treated as
untrusted until its exact source, license, privileges, behavior and integration
boundary are reviewed.

The catalog is `config/upstream/software-catalog.yaml`.

## Integration modes

Each project uses exactly one mode:

| Mode | Meaning |
| --- | --- |
| `reference_only` | inspect ideas and protocols; copy and execute nothing |
| `independent_reimplementation` | implement from public specifications without copied incompatible code |
| `native_library` | link a small pinned and reviewed dependency |
| `vendored_component` | store selected reviewed source with provenance and patch tracking |
| `external_service` | run as an isolated process/container behind a contract |
| `firmware_image` | distribute and boot as separate firmware with isolated credentials |
| `remote_adapter` | connect to an independently managed installation |

Large Linux-oriented applications default to `external_service` or
`remote_adapter`, not Cardputer firmware.

## Intake workflow

1. Define one bounded capability objective.
2. Record owner, repository, default branch and exact reviewed commit.
3. Inspect releases, languages, build system, manifests, tests and maintenance.
4. Confirm runtime and hardware compatibility.
5. Review the repository and relevant dependency licenses.
6. Threat-model inputs, network, secrets, files, devices, privilege, updates,
   parsers and binary execution.
7. Select one integration mode and an isolation/removal plan.
8. Build one sandboxed proof of concept with synthetic or owned data.
9. Include a negative control and record commands and resource use.
10. Approve, reject or quarantine explicitly.

A rejected project remains in the catalog with its reason.

## Prohibited intake behavior

Do not:

- execute installation scripts directly from a URL;
- run unreviewed shell pipelines;
- trust popularity as a security signal;
- accept generated binaries without verification;
- use floating production branches or dependency versions;
- silently add network destinations;
- introduce privileged containers without justification;
- copy code without preserving provenance and notices;
- disable security checks to make upstream code work;
- expose Tomato Sentinel credentials to separate firmware.

## Bruce

Bruce is one upstream candidate and receives no exception to this policy.

The initial preferred relationship is a separate firmware image launched
through a boot manager. Native or vendored integration requires memory,
storage, licensing, security, recovery and peripheral-isolation review plus an
ADR.

No Bruce source may be copied until its exact origin and license obligations
are recorded.

## Proof-of-concept requirements

A proof of concept:

- uses no production credentials;
- accesses only synthetic, owned or explicitly authorized targets;
- has bounded time, network and storage;
- runs without privilege where practical;
- records the exact commands executed;
- records a negative control;
- can be removed without changing core business logic.

## SBOM and updates

Release artifacts record direct and transitive components, versions,
repositories, commits, checksums, licenses, build environment and produced
artifact.

An upstream update triggers revalidation; it is never merged automatically:

```text
change detected
    -> catalog status revalidation_required
    -> changelog/diff/license/permission review
    -> tests
    -> SBOM regeneration
    -> accept or reject
```

# Software bill of materials

`python-development.cdx.json` is the CycloneDX 1.5 snapshot generated from the
committed `uv.lock` for the foundation development environment.

Regenerate it with the exact approved uv version:

```text
uv export --locked --all-groups --preview-features sbom-export \
  --format cyclonedx1.5 \
  --output-file sbom/python-development.cdx.json
```

The current uv SBOM exporter is marked experimental. Review generated changes,
including transitive dependencies, before committing. Release SBOMs will be
generated separately for each deployable artifact.

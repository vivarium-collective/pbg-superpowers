# pbg-* distribution convention

Every `pbg-*` wrapper package SHOULD publish to PyPI when the underlying
simulator is installable. This makes pbg-* packages first-class Python
dependencies that consumers can `uv pip install pbg-<tool>` from anywhere
— no submodule juggling, no `[tool.uv.sources]` mappings, no broken CI
when sub-submodules have orphan gitlinks.

## When PyPI publishing is required

- The underlying simulator is itself pip-installable (with or without
  compiled native deps), OR
- The pbg-* wrapper is pure-Python and stands alone

## When git-only is acceptable (with explicit justification)

- The simulator has proprietary licensing that prevents redistribution
- The simulator requires a manual binary installation outside pip
- The wrapper has unstable APIs that aren't ready for PyPI

In these cases, the repo's README MUST document the constraint and the
catalog entry MUST omit `pypi_name`.

## Distribution naming

- Repo name = PyPI distribution name = `pbg-<tool>` (kebab-case)
- Python import name = `pbg_<tool>` (underscores)
- Tag releases as `v<MAJOR>.<MINOR>.<PATCH>` (semver)

## Minimum `pyproject.toml`

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "pbg-<tool>"
version = "0.1.0"
description = "Process-bigraph wrapper for <Tool>"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [{name = "Your Name", email = "you@example.com"}]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: Scientific/Engineering :: Bio-Informatics",
]
dependencies = [
    "bigraph-schema>=0.0.60",
    "process-bigraph>=0.0.66",
    "<tool>",  # the underlying simulator from PyPI
]

[project.urls]
Homepage = "https://github.com/vivarium-collective/pbg-<tool>"
Issues = "https://github.com/vivarium-collective/pbg-<tool>/issues"

[tool.hatch.build.targets.wheel]
packages = ["pbg_<tool>"]
```

## Release workflow

`.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags: ["v*"]
permissions:
  id-token: write   # for PyPI trusted publishing
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - name: Install uv
        run: pip install uv
      - name: Build
        run: uv build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

The first publish requires PyPI trusted publishing setup for the repo.
See https://docs.pypi.org/trusted-publishers/.

## uv enforcement

Workspaces created via pbg-template MUST use `uv venv` (not
`python -m venv`). Rationale: uv is faster, handles modern lockfiles
better, and the catalog Install logic uses `uv pip install --python
<venv-py>` to install pbg-* packages from PyPI or local paths.

Scaffolded workspaces' `NEXT_STEPS.md.j2` and `template-init.sh` use uv
exclusively. Skills (`/viva-workspace`, `/viva-workbench`) follow suit.

## Verification

The maintainer audit script checks whether a repo is published on PyPI:

```
python scripts/audit-pbg-repo.py pbg-tellurium
# Audit output includes "published on PyPI: PASS (v0.3.2)" or similar.
```

(Replaces the v0.8 `/pbg-package` skill.)

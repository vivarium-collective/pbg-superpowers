---
name: pbg-package
description: Audit a pbg-* repo's pyproject.toml + discovery contract + install smoke. Reports findings; does NOT modify the target repo.
arguments:
  - name: repo
    description: Path to a local pbg-* repo OR vivarium-collective repo name (e.g. pbg-smoldyn)
    required: true
---

# /pbg-package <repo>

Audit a `pbg-*` package against the convention pbg-template / pbg-superpowers expects.

## What it checks

1. `pyproject.toml` exists with `[project]` table
2. `[project].dependencies` includes `bigraph-schema` (auto-discovery requirement)
3. `[project].dependencies` includes `process-bigraph` (Process/Step base classes)
4. `[project].requires-python` is declared (best practice; otherwise users hit version-wheel mismatches)
5. At least one `process_bigraph.Process` or `process_bigraph.Step` subclass exists in the package
6. (Optional) `pip install -e .` succeeds in an ephemeral venv (this is slow; skip if `--no-install` passed)

## How to run

```
/pbg-package pbg-smoldyn          # clone vivarium-collective/pbg-smoldyn to tmp, audit
/pbg-package ~/code/pbg-cobra     # audit local checkout
/pbg-package pbg-readdy --no-install   # skip the install smoke (faster)
```

## Output

For each check, print PASS / WARN / FAIL with a one-line reason. End with a summary table:

```
=== Audit: pbg-smoldyn ===
pyproject.toml                    PASS
[project].dependencies: bigraph-schema   FAIL  — not declared
[project].dependencies: process-bigraph  PASS
[project].requires-python                FAIL  — not declared; recommend ">=3.10,<3.12" given smoldyn wheel availability
Process/Step subclasses           PASS  — found 1: SmoldynProcess
pip install -e .                  FAIL  — smoldyn has no cp312 wheels (matches dashboard install error)

=== Summary ===
PASS: 3, WARN: 0, FAIL: 3
Recommended fixes:
- Add `bigraph-schema>=0.0.60` to [project].dependencies
- Add `requires-python = ">=3.10,<3.12"` to [project]
```

## Constraints

- Read-only against the target repo. Do NOT write or commit anything to it.
- If `--no-install` is passed, skip the slow smoke test.
- Audit-only for now. A future v0.4.6 may add `--apply` to open PRs.

## Implementation

When invoked, run:

```python
python -m pbg_superpowers.package_audit <repo> [--no-install]
```

The skill should:
1. Detect whether the argument is a local path or a repo name
2. If a name: shallow-clone from `https://github.com/vivarium-collective/<name>.git` into a temp dir, audit, and clean up
3. Print the structured report and exit with code 0 (all pass/warn) or 1 (any FAIL)

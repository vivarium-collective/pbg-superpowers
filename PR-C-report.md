# PR-C report — viva-superpowers deletes + console_scripts prune + prose

Branch `chore/phase2-prep-deletes`, worktree `/Users/eranagmon/code/pbg-superpowers--phase2-prep`.
Commit range: `077c2c9..7032133` (single commit `7032133`), pushed to
`origin/chore/phase2-prep-deletes`.

## C.2 — delete

`git rm` the 7 modules + their tests exactly as listed in the plan
(including `roll_up`'s test being `tests/test_roll_up_sync.py`, not
`test_roll_up.py`). All 14 files existed and were removed cleanly:

- `viva_superpowers/parameter_validation.py` + `tests/test_parameter_validation.py`
- `viva_superpowers/plot_style.py` + `tests/test_plot_style.py`
- `viva_superpowers/calibration_sweep.py` + `tests/test_calibration_sweep.py`
- `viva_superpowers/figure_refresh.py` + `tests/test_figure_refresh.py`
- `viva_superpowers/package_audit.py` + `tests/test_package_audit.py`
- `viva_superpowers/runs_index.py` + `tests/test_runs_index.py`
- `viva_superpowers/roll_up.py` + `tests/test_roll_up_sync.py`

`viva_superpowers/chart_store.py:20` comment updated to name `refresh_viz`
only (dropped the `figure_refresh` mention).

## C.3 — prose edits (same commit)

- `skills/viva-viz/SKILL.md:39` — removed "Prefer the framework house style
  `viva_superpowers.plot_style` (...)"; replaced with plain palette-consistency
  guidance, no module reference.
- `skills/viva-study/SKILL.md:65` — removed the "use
  `viva_superpowers.calibration_sweep`" module pointer; kept the surrounding
  CALIBRATE-WITH-A-SWEEP guidance intact.

Both are flagged in the commit message as **capability removals**, per the
plan's instruction to call them out explicitly.

## C.4 — console_scripts prune

Deleted exactly the 5 lines from `pyproject.toml [project.scripts]`:
`viva-migrate-readouts`, `viva-populate-simulation-set`,
`viva-populate-findings`, `viva-roll-up`, `viva-canonicalize-investigations`.
Diff matches the plan's D1 table 1:1 — no other script lines touched.

## C.5 — verify

- `uv sync --extra dev` — resolved and installed cleanly (83 packages).
- `PYTHONPATH=$PWD uv run python -c "import viva_superpowers; print(...)"`
  → resolved to the **worktree** path, confirmed.
- `PYTHONPATH=$PWD uv run pytest -q` (with `--extra dev --extra evaluator
  --extra processes --extra events` also synced, since the plan's bare
  `--extra dev` undercounts optional-dependency-gated test modules —
  `polars` via the `evaluator` extra, `investigation_contracts` via `events`,
  `pbg_basic_processes` via `processes`; none of these extras were touched
  by this PR):
  **1282 passed, 22 skipped, 7 failed.**
  All 7 failures are **pre-existing and unrelated** to this PR — confirmed
  by `git stash`-ing this PR's changes and re-running the same 7 tests
  against the untouched tree: identical 7 failures, identical assertion
  messages. They fall into two pre-existing-environment buckets:
  - `test_linkage_index_golden.py` (2), `test_readout_migration.py` (2) —
    depend on a "real" dnaa study / bib data on this machine
    (`_find_real_dnaa_study()`) that has apparently drifted since these
    goldens were captured; nothing to do with the deleted modules.
  - `test_workspace_scaffold.py`, `test_workspace_scaffold_snapshot.py`,
    `test_workspace_schema_sync.py` — depend on an external `pbg-template`
    checkout that has drifted from the pinned snapshot (e.g. an unexpected
    `./docs/first-run-agent-guide.md` in the live template vs. the
    committed manifest). Also unrelated.
- Dangling-reference grep (`grep -rnE "\b(parameter_validation|plot_style|
  calibration_sweep|figure_refresh|package_audit|runs_index|roll_up)\b" ...
  | grep -v roll_up_acceptance | grep -v roll_up_verdict`) → **2 hits,
  both false positives, not fixed** (out of scope for the "do exactly C.2-C.4"
  instruction):
  1. `viva_superpowers/linkage_index.py:408` — comment "`# roll_up preserves
     criterion order`" describing the *behavior* of `roll_up_acceptance`
     (imported 3 lines above from `.investigation_status`, which stays) —
     bare word "roll_up" in prose, not a reference to the deleted module.
  2. `skills/viva-report/SKILL.md:86` — "written by `figure_refresh`/
     `refresh_viz`" — the plan's own Task-0 table for `figure_refresh`
     explicitly predicted this ("only §4 (descriptive) + a comment at
     chart_store.py:20") and only required editing the `chart_store.py`
     comment (done) and the two named SKILL.md sentences for `plot_style`/
     `calibration_sweep` (done) — it did not list this line for editing.
     Left as-is per the "do exactly C.2-C.4" scope; flagging for the
     maintainer to decide whether to fold into this PR or a follow-up.
- Entry-point resolution: all **9** remaining `viva-*` console_scripts load
  successfully (`viva-backfill-runs`, `viva-canonicalize-studies`,
  `viva-citation-gaps`, `viva-compute-outcomes`, `viva-feedback-import`,
  `viva-migrate-inputs`, `viva-migrate-nested`, `viva-scaffold`,
  `viva-sync-runs`); confirmed the 5 dropped names are absent from
  `entry_points(group='console_scripts')`.

## C.6 — downstream regression gate

**v2ecoli--main audit gate: blocked by a pre-existing, unrelated issue —
not run to completion; fell back to the plan's explicit fallback path.**

Attempted the literal C.6 recipe against
`/Users/eranagmon/code/v2ecoli--main` (read carefully as a **shared
canonical checkout** — never committed there; only `uv sync` /
`uv pip install --no-deps` against its own `.venv`, and `git status`
confirmed clean before and after). Findings:

- `uv sync --extra dev --no-install-package vivarium-workbench` succeeded
  and left the git tree clean (no `uv.lock`/`pyproject.toml` drift).
- Installing this PR's worktree build with `uv pip install -e
  /Users/eranagmon/code/pbg-superpowers--phase2-prep --no-deps` initially
  appeared to succeed but a **stale, pre-existing physical
  `viva_superpowers/` package copy already present in v2ecoli--main's
  `.venv/lib/.../site-packages/`** (dated Jul 31, unrelated to today's
  work) was not cleaned by the editable install and shadowed the new
  editable pointer. After explicitly removing the stale directory + dist-info
  + `.pth` and reinstalling, `roll_up` correctly became unimportable —
  confirming the editable install genuinely reflects this PR's deletions.
- Running the audit gate itself then failed **uniformly across all 56
  studies** with `unresolved composite(s)` — traced to
  `v2ecoli/__init__.py` importing `from viva_superpowers.composite_generator
  import _REGISTRY, build_generator`, which in turn does
  `from process_bigraph.composite_generator import *` — a submodule that
  does not exist in the `process-bigraph` version v2ecoli--main's own
  `uv.lock` pins (**1.5.0**, commit `ebea120f`, vs. `1.8.2` used by this
  worktree's own `uv sync`). Restoring v2ecoli--main's own locked
  dependency (`uv sync` without our override) reproduces the identical
  failure with v2ecoli's *originally pinned* `pbg_superpowers==0.16.0`
  (pre-rebrand dist name) — proving this is **v2ecoli--main's own
  stale-lockfile problem** (matches the known "uv-lock CI illusion vs
  branch tip" pattern: `git branch=main` sources pin a resolved commit,
  not the live branch tip), entirely independent of this PR's deletions.
  v2ecoli--main's git tree was left untouched (clean `git status`) and its
  `.venv` was restored to its own `uv sync`-resolved state before finishing.

Per the task's explicit fallback ("if v2ecoli sync is heavy, at minimum run
the 3 import smokes... in a venv with THIS worktree installed"), ran the 3
script-consumer import smokes directly against this worktree's own `uv run`
environment:

```
from viva_superpowers.runner import pbg_runner            # ok
from viva_superpowers.run_registry import register_run    # ok
from viva_superpowers.study_evaluator import evaluate_test # ok
```

All three pass. Additionally, `tests/test_study_audit.py` (8 tests) passed
in the full in-repo pytest run, exercising `study_audit`'s own logic
end-to-end without the v2ecoli lockfile obstruction.

**Concern for the maintainer:** the v2ecoli--main workbench-free audit gate
could not be verified end-to-end in this session because v2ecoli--main's
own `uv.lock` is stale relative to both `process-bigraph` main and its own
source's `viva_superpowers` import (still pinning the pre-rebrand
`pbg_superpowers` package). This is pre-existing and orthogonal to PR-C,
but it means the "one gate that matters" (per the plan's own words) is
currently un-runnable as scripted until v2ecoli--main's lockfile is
refreshed — worth flagging as a separate follow-up, possibly urgent since
it also means v2ecoli's actual CI `audit-gate` job may currently be running
against a resolution that doesn't match its own source tree.

## Files touched

- `/Users/eranagmon/code/pbg-superpowers--phase2-prep/pyproject.toml`
- `/Users/eranagmon/code/pbg-superpowers--phase2-prep/skills/viva-viz/SKILL.md`
- `/Users/eranagmon/code/pbg-superpowers--phase2-prep/skills/viva-study/SKILL.md`
- `/Users/eranagmon/code/pbg-superpowers--phase2-prep/viva_superpowers/chart_store.py`
- 14 deleted files (7 modules + 7 tests, listed above under C.2)

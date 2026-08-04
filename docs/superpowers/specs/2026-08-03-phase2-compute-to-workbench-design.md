# Phase 2 — Compute → workbench (de-vendor the plugin)

*Design doc · 2026-08-03 · Phase 2 of the viva-superpowers re-architecture. Rewritten after an adversarial simplification review (Fable) of the first draft — which cut a proposed `viva-core` package and a skills→HTTP rewire as over-engineered.*

## Goal
Get the *dashboard compute* out of the `viva_superpowers` plugin and into the `vivarium-workbench` server that already renders it — and **drop the workbench's dependency on the plugin**. Shrink the plugin toward "skills + a small workbench-free contract library." Nothing downstream (~1,829 files) may break.

## End-state: 2 active homes (+ the engine)
- **process-bigraph** — engine substrate (Phase 1, done).
- **vivarium-workbench** — dashboard compute + server. **Stops depending on `viva_superpowers`.**
- **viva-superpowers** — agent skills (SKILL.md) + a small **workbench-free** importable core (~3.7K LOC / 8 modules) that v2ecoli/sms-ecoli genuinely import.

**No `viva-core` package.** The downstream-imported surface is ~3.7K LOC consumed by one repo family (v2ecoli + its fork sms-ecoli). A new PyPI package + release cadence + a third back-compat shim layer (on a dist name — `pbg-superpowers` — that consumers still haven't migrated off) is not a proportionate price. If "pure skills" still matters after the workbench sever lands, the rename is an afternoon at 3.7K LOC with real information in hand. Ship the reversible decision first.

## The real win: de-vendoring
The workbench today **both** declares `pbg-superpowers>=0.14.0` as a mandatory dep (`vivarium-workbench/pyproject.toml:38`) **and** keeps byte-mirrored *vendored copies* of plugin modules in `vivarium_workbench/lib/` — `viz_freshness`, `refresh_viz`, `runs_index`, `backfill_runs`, `investigation_inputs`, `run_registry` — guarded by 5 drift tests. Every header says "the dashboard venv has no viva_superpowers." Phase 2 collapses each duplicate pair to **one** implementation inside the workbench and deletes the plugin dep, the vendored copies, the mirror tests, and ~50 `try/except ImportError` guards. Version-skew (a `_REGISTRY` break hid for ~3 weeks behind a git-branch pin) stops being possible.

## Facts that shape the plan (verified against the post-Phase-1 tree)
- The workbench has **96** `viva_superpowers` import statements across 54 files, but only **2** are top-level; 81 are function-local + `try/except`-guarded → severing is far cheaper than the 25.5K-LOC number implies.
- **~40% of that coupling is already just Phase-1 shims** (`composite_generator` is a 9-line re-export, etc.). Repointing those imports at `process_bigraph` is mechanical and needs no home decision — Phase 1 left every consumer importing through shims.
- **Hard constraint:** v2ecoli CI (`.github/workflows/ci.yml:188`) runs `python -m viva_superpowers.study_audit --gate` installed with `--no-install-package vivarium-workbench`; `study_audit.py` "MUST NOT import vivarium_workbench." → the L0–L5 audit lives in a workbench-free, pip-installable package **forever**.
- **14 `console_scripts`** (`viva-compute-outcomes`, `viva-sync-runs`, `viva-canonicalize-*`, …) are a public API — `python -m`/entry-point consumers are invisible to import greps.
- Tests are ≈1:1 with source (~23.8K LOC). Every module move carries its tests in the same commit.

## What STAYS importable in viva-superpowers (workbench-free core, ~3.7K LOC)
| Module(s) | LOC | Consumer |
|---|---|---|
| `study_audit` + `study_canonicalize` + `study_io` | 1,104 | v2ecoli CI `audit-gate` (workbench-free, hard) |
| `study_evaluator` + `readout_resolver` | 1,749 | v2ecoli/sms tests |
| `runner` | 235 | `scripts/run_default_baseline.py` |
| `run_registry` | 191 | `scripts/run_condition_multigen_parquet.py` |
| `provenance` | 239 | `python -m viva_superpowers.provenance` + `scripts/_run_provenance.py` |
| Phase-1 shims (`composite_generator`/`visualization`/… ~208 LOC) | 208 | 8 repos import nothing else — keep indefinitely |

## Delete list — do FIRST (verified zero consumers; ~3,563 src + 2,222 test = ~5.8K LOC, 23%)
`parameter_validation` (284, zero refs) · `calibration_sweep` (456) · `figure_refresh` (188) · `plot_style` (163) · `package_audit` (252, → `scripts/` if wanted) · `backfill_runs` (238, workbench has its own) · `migrate_inputs` (180) · `migrate_nested` (127) · `roll_up` (111) · `event_client` (75) · `runs_index` (43, workbench vendors its own) · `readout_migration` (349, sever from `report_linter` first) · `dashboard.py` (25, alias shim) · `workbench.py` (1,054, replaced by `vivarium-workbench serve`) · `intervention` (18, after repointing `pbg-autopoiesis`).
- **NOT** a "readout-validator quintet consolidation" — that reduces to `rm parameter_validation.py`. The feedback-trio merge is real but happens **inside the workbench after the move**, never in the same commit as a relocation.

## Sequencing (2 sub-phases)

### Phase 2.0 — prep (no design decisions; independently valuable; merge immediately)
1. Delete the 15 dead modules + their tests.
2. Repoint the workbench's ~38 shim imports at `process_bigraph`; also the string templates that emit `from viva_superpowers…` into user files (`lib/viz_write_mutations.py:237,257`, `lib/notebook_export.py:312,414`).
3. Fix `pbg-autopoiesis`'s 4 import sites (sole consumer of `viz_freshness`/`ablation`/`intervention`/non-workbench `generation`; 2 already `try/except`-optional) — repoint or vendor.
4. Prune `console_scripts` to those with real consumers.
- Result: package 25.1K→~19K; workbench coupling 28 modules/96 stmts → 24/58. Ship it.

### Phase 2.1 — the move (de-vendor into the workbench)
Move the 24 workbench-only modules + tests into `vivarium_workbench/lib/` in **dependency order** (`study_io` → `study_outcomes`/`study_verdict` → `rigor`/`report_linter` → `needs_attention`(8 deps)/`linkage_index`(deps) last). Per commit: land the canonical module, **delete the vendored copy + its mirror test in the same commit**, merge with the existing workbench twin so there is one implementation (`study_verdict` predicate already "EXACTLY matches `lib/investigations_index._condition_satisfied`"; `runner` mirrors `lib/composite_runs`; `runs_index` mirrors `lib/simulations_index`). Add `vwb` subcommands for the skill-invoked file ops. Rewire skills. Drop `pbg-superpowers` from `vivarium-workbench/pyproject.toml`.
- **There is no 2c** ("plugin = skills only" is the *result*, not a step). **There is no 2a** (nothing moves for downstream — viva-core is gone).

## The skills↔workbench boundary (keep the working one)
The skills' current split is empirically correct — keep it. **Rule:** HTTP when the skill needs live server state (runs in flight, the catalog the server holds, chart cache, session); **CLI (`vwb <verb>`)** when the op is a pure function of the workspace directory. The 9 file-compute `python -m viva_superpowers.X` sites (`study_verify`, `study_outcomes`, `study_narrative`, `study_findings`, `seed_from_followup`, `report_linter`, `citation_gaps`, `investigation_close`, `migrate_inputs`) become `vwb` subcommands — no new HTTP endpoints. The 4 bootstrap ops (`workbench start|stop|status`, `scaffold workspace`, `workspace_catalog add`, `paths --env`) are structurally pre-server and stay CLI regardless.

## Robustness (close these holes)
- **Consumer-map method (mandatory):** grep **both** `viva_superpowers` AND `pbg_superpowers` (sms-ecoli + pbg-autopoiesis import *only* via the deprecated alias — a `viva_superpowers`-only grep returns zero and would wrongly clear them); **dedupe forks** (sms-ecoli is a v2ecoli fork — identical paths/line-numbers); include **`python -m` + console-scripts + generated files** (v2ecoli's CI gate, the `provenance` CLI, `viva-human-atlas/reports/published/**` generated imports); exclude sibling-worktree noise (`vwb-*`, `v2e-*`) and name-collisions (v2ecoli's own `runner.py`/`provenance.py`).
- **Dependency enforcement:** add an import-linter forbidden contract (the workbench already runs import-linter, `pyproject.toml:127`): `viva_superpowers ✗→ vivarium_workbench`, and after the sever `vivarium_workbench ✗→ viva_superpowers`. The *real* guard is v2ecoli's `audit-gate` job (live, external, workbench-free install check) — keep it green throughout.
- **Break the test-only cycle:** the plugin's own tests import the workbench (`tests/test_integration_observable_pipeline.py:143`, `test_linkage_index_golden.py:95`, `test_workspace_paths.py:36`), and `vivarium_workbench/server.py` is a 42-line shim re-exporting `_build_iset_summary_for_test` for them. **Exit criterion:** plugin suite has zero `vivarium_workbench` refs and that `server.py` shim is deleted.
- **Mirror-test hazard:** the 5 drift tests read `../pbg-superpowers/viva_superpowers/<mod>.py` from a sibling checkout — their meaning depends on which worktree is on disk. Delete each in the commit that lands its canonical.

## Success criteria
1. `vivarium-workbench/pyproject.toml` has **no** `pbg-superpowers`/`viva-superpowers` dependency; import-linter forbids the edge; the 6 vendored copies + 5 mirror tests are gone.
2. Plugin suite has zero `vivarium_workbench` references; `server.py` test-shim deleted.
3. v2ecoli `audit-gate` (workbench-free) stays green; `python -m viva_superpowers.study_audit` + the 8-module core still import with `vivarium-workbench` absent.
4. Package ≥40% smaller; one implementation per formerly-duplicated module.

## Deferred (not this phase)
- Renaming the ~3.7K-LOC importable core into its own dist (the old `viva-core` idea) — revisit after the sever, with real information; it's an afternoon then.
- The feedback-trio merge — inside the workbench, after the move.
- The Phase-1 `_SKIP_SEGMENTS` self-walk edge case (downstream workspace colocating `pkg/tests/`).
- Finishing the `pbg-superpowers` → `viva-superpowers` dist-name migration across the 4 consumers (orthogonal, but Phase 2 shouldn't assume it's done).

## Open decisions for maintainer
- **D1 — console_scripts pruning:** which of the 14 to keep? (Keep the ones with real `python -m`/entry-point consumers; drop the rest.)
- **D2 — `package_audit`:** move to `scripts/` or delete outright?
- **D3 — the 8-module core's eventual name:** stay in `viva_superpowers` (this phase) vs. a later rename — confirm "later" is acceptable.

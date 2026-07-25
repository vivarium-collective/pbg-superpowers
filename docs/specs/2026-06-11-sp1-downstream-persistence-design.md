# SP1 — Downstream Persistence — Design

> Sub-project #1 of the [Active Investigation Framework](2026-06-11-active-investigation-framework-design.md) program (Layer 1, Propagate). Closes the verified downstream-persistence gaps so verdicts/acceptance/runs/param-drift are written to disk automatically, not just recomputed at render-time.

## Goal

Complete the run → verdict → acceptance → param-drift persistence path so the information a run produces is durably written to the YAML (and therefore carried by exports, the read-only snapshot, and `/pbg-report`), and the already-built `enforced_params` drift detector actually fires.

## Verified current state (grounded 2026-06-11)

- ✅ **Study `gate_evaluator` is already persisted.** `study_outcomes.sync()` chains `record_runs → compute_outcomes → populate_simulation_set → write_gate_evaluator → populate_finding_observations` (`study_outcomes.py:160-191`). The study verdict is written to disk on every post-run sync. **Not a gap** — do not duplicate it.
- ❌ **Investigation acceptance is not auto-written.** `investigation_status.write_investigation_acceptance(inv_dir, workspace)` exists (`investigation_status.py:127`) but is called only by the orphaned `roll_up.py` CLI (`roll_up.py:81,99`). When a member study's verdict changes via `sync()`, the parent investigation's `computed_acceptance` on disk goes stale.
- ❌ **`enforced_params` has no writer.** It is read by `param_enforcement.load_enforced_params` (`param_enforcement.py:109`) and `server.py:1590,1605` (load + check + render + lint), but nothing in any repo writes the field. The drift detector is fully wired and never fires.
- ❌ **`backfill` is not auto-triggered.** `record_runs` records the just-completed run; on-disk runs created outside the dashboard (or pre-existing) are never reconciled into `study.yaml runs[]`.

## Design

Four small, independent wirings. All new logic is deterministic and lives in `viva_superpowers/`; the vivarium-workbench post-run hook (the existing `study_outcomes.sync()` call sites, `server.py:~5036/5057/5419`) calls them. All writes are code-owned slots, fill-absent-only, never clobbering authored values, via the ruamel round-trip already used by `study_outcomes`.

### 1. Investigation acceptance auto-write
- Add `sync_investigation(inv_dir, workspace=None) -> dict` to `viva_superpowers/study_outcomes.py` (or `investigation_status.py`): a thin best-effort wrapper that calls `write_investigation_acceptance(inv_dir, workspace)` and returns a summary.
- Wire the dashboard post-run hook so that after a study's `sync()`, if the study belongs to an investigation, it also calls `sync_investigation(parent_inv_dir)`. The hook already resolves the study path; resolve its parent investigation via `WorkspacePaths` (nested `investigations/<inv>/studies/<slug>/`).
- Study `sync()` stays study-scoped (no upward coupling); the investigation step is composed at the hook level where the investigation context is known.

### 2. `enforced_params` population + activation
- Add `derive_enforced_params(study_spec) -> list` to `viva_superpowers/param_enforcement.py`: returns the param **names** the study explicitly declares — the union of keys in each `baseline[].params` and each `variants[].parameter_overrides` (the params the study deliberately controls).
- Add `populate_enforced_params(study_dir) -> dict`: if `enforced_params` is absent, write the derived set (fill-absent, author-overridable) via the ruamel round-trip; idempotent.
- Add `populate_enforced_params` as a best-effort step in `study_outcomes.sync()` (after `record_runs`, before/with the detector). The existing `server.py` check path (`load_enforced_params` → `check_enforced_params`) then fires and surfaces violations.
- **Field shape:** `enforced_params:` is a list of param names (matching what `load_enforced_params` already expects at `param_enforcement.py:109`). Confirm the expected shape during implementation and match it exactly.

### 3. `backfill` reconcile
- Add an idempotent reconcile to the record path: any completed on-disk run (zarr/parquet/sqlite, discovered the same way the SimulationsDB view does via `simulations_index`/`backfill_runs`) that is absent from `study.yaml runs[]` is registered (fill-absent). Fold into `record_runs` or add `reconcile_runs(study_dir)` called first in `sync()`.
- Reuse the existing `backfill_runs` discovery logic rather than re-implementing run discovery.

### 4. `roll_up.py` disposition
- Keep `roll_up.py` as the manual/bulk re-persist entry (e.g. re-stamp all investigations after a schema change). The auto path (1 + the existing `sync()`) covers the common case.
- Its `write_gate_evaluator` arm duplicates `sync()`; leave it (harmless, useful for bulk) or trim only if it stays clean. Do **not** delete `roll_up.py` (it is the bulk tool, now no longer the *only* path).

## Constraints
- Deterministic-in-pbg-superpowers; the dashboard only calls these functions (AI-free rule).
- Code-owned slots, fill-absent, ruamel round-trip — never clobber authored `enforced_params`/acceptance/runs.
- Best-effort steps in `sync()` (errors captured, never raised) — `record_runs` must always complete, matching the existing pattern.
- Idempotent: a second sync writes nothing new.

## Testing
- `derive_enforced_params`: a study with baseline params {a,b} + variant overrides {b,c} → enforced = [a,b,c]; empty study → [].
- `populate_enforced_params`: fills when absent; no-op when authored; idempotent.
- `sync_investigation`: writes `computed_acceptance`; idempotent; best-effort (bad inv dir → captured error, not raised).
- `reconcile_runs`: an on-disk run absent from `runs[]` gets added; present runs untouched; idempotent.
- A golden on v2e-invest (read-only / tmp copy): after a study sync, the parent investigation's `computed_acceptance` is written and `enforced_params` is populated.

## Non-goals
- No new verdict math — reuse `roll_up_verdict` / `roll_up_acceptance` / `check_enforced_params`.
- No clobbering authored values; no UI changes beyond what already renders these fields.
- Sweep/seeds execution, readout vocabulary, navigation, guidance — later sub-projects.

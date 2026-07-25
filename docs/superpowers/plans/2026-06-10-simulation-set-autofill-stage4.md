# Simulation-set auto-fill (spine stage #4) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Auto-populate the often-blank `simulation_set` block in a study from what's actually defined + run (baseline, variants, runs[]) — **deterministic Python in pbg-superpowers**, mirroring `study_outcomes.record_runs`. The dashboard calls it via `sync` and merely renders the result (NO AI in the dashboard — see memory `feedback_dashboard_ai_free`).

**Architecture:** New `viva_superpowers/simulation_set.py`: `derive_entries(spec)` builds simulation_set entries from `conditions.baseline`/`baseline[]` + `conditions.variants`/`variants[]` + `runs[]`; `populate_simulation_set(study_dir)` reconciles them into study.yaml via a **ruamel round-trip** (comment-preserving), **conservatively**: fill-when-absent on existing authored entries (NEVER overwrite an authored value), full-derive + append for new entries, **never delete authored entries**. Wired into `study_outcomes.sync`. The read-time derivation already exists at `vivarium-workbench/lib/investigations.py:388-416` (baseline+variants → in-memory simulation_set) — this PERSISTS that mapping and extends it with run-derived fields.

**Tech:** Python 3.11+, ruamel.yaml, pytest. `.venv/bin/python`. Spec: the spine grounding (this plan is self-contained).

**Field ownership** (decided):
- **Code-owned (derivable):** `name` (identity), `kind`, `base_model` (clean dotted path), `seeds`, `perturbation`/`params`, `status`, `metrics`, `pass_fail_tests`/`applies_tests`.
- **Authored (NEVER touched):** `description`, `notes`, `condition`, the free-text `sweep:` string, `candidate_selection`, sweep results (`aggregate_metrics`/`candidates_selected`/`rejection_reasons`/`runs`), `readouts`, and any field already present on an authored entry.
- **Policy:** existing entry (matched by `name`) → set only code-owned fields that are ABSENT (fill gaps; never overwrite). No matching entry → append the full derived entry. Never delete an authored entry the deriver didn't produce.

---

## File map
- Create: `viva_superpowers/simulation_set.py`.
- Modify: `viva_superpowers/study_outcomes.py` (`sync` also calls `populate_simulation_set`, best-effort) + `pyproject.toml` (optional `pbg-populate-simulation-set` CLI / or extend the sync CLI).
- Test: `tests/test_simulation_set.py`.

---

## Task 1: `derive_entries(spec)`
- [ ] **Step 1: Failing tests** — given a spec with `conditions.baseline.composite = "v2ecoli.composites.baseline.baseline"` + `params.perturbations`, two `conditions.variants[]` (each `name`/`base_composite`/`parameter_overrides`), and `runs[]` (with `seeds`, `status: completed`, `outcomes: {testA: {result: PASS}}`), `derive_entries(spec)` returns: a `<baseline-name>-baseline` entry `{kind: single, base_model, is_baseline: true, perturbation, seeds (union from runs), status}` + one entry per variant `{name, kind, base_model (composite|base_composite|baseline), perturbation: parameter_overrides, metrics (study readout names), pass_fail_tests (run outcomes keys ∩ behavior_tests/tests names), status}`. Also handle the legacy top-level `baseline[]`/`variants[]` (not just `conditions.`).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `derive_entries(spec)` + helpers `_seeds_from_runs(runs)` (union of `runs[].seeds`, deduped/sorted), `_status_from_runs(runs)` (`completed`→`ran`, else `ready`), `_metric_names(spec)` (readout names), `_test_names(spec)` (behavior_tests/tests names), `_pass_fail_from_runs(runs, test_names)` (outcomes keys ∩ test_names). Mirror `investigations.py:388-416` for the baseline/variant shape.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(simulation_set): derive_entries from baseline/variants/runs`

## Task 2: `populate_simulation_set(study_dir)` (conservative, comment-preserving)
- [ ] **Step 1: Failing tests** (load study.yaml from RAW TEXT with comments): 
  - (a) a study with NO `simulation_set` + a baseline + 2 variants + runs → after populate, `simulation_set` has the baseline + 2 variant entries with code-owned fields; comments elsewhere preserved byte-for-byte; returns `{added: 3, updated: 0}`.
  - (b) an existing authored entry with a hand-written prose `base_model` and a `notes:` → populate FILLS its absent `seeds`/`status` but does NOT overwrite the authored `base_model`/`notes`; `updated` counts only gap-fills.
  - (c) an authored entry whose `name` the deriver doesn't produce → left untouched (never deleted).
  - (d) idempotent: second populate is byte-identical, returns `{added:0, updated:0}`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `populate_simulation_set(study_dir)` — load via `study_io.load_yaml_mapping`; `derived = derive_entries(spec)`; index existing `simulation_set` by name; for each derived entry compute added (no match) / updated (match has ≥1 absent code-owned field the derive can fill); only if changed call `_write_simset_preserving_comments` (clone of `study_outcomes._write_runs_preserving_comments` retargeted to `rt_spec["simulation_set"]`: matched entries get only ABSENT code-owned keys set; new entries appended; authored entries/keys untouched). NEVER fabricate (no runs/baseline → derive what's available; empty derive → no write).
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(simulation_set): populate_simulation_set (conservative ruamel write)`

## Task 3: Wire into `study_outcomes.sync` + CLI
- [ ] **Step 1: Failing test** — `study_outcomes.sync(study_dir)` now also runs `populate_simulation_set` (best-effort, same try/except pattern as the compute_outcomes wiring): returns `summary["simulation_set"] = {added, updated}`; on error → `{"error": ...}` (record_runs/compute still complete). 
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — in `sync`, after compute_outcomes, `try: from .simulation_set import populate_simulation_set; summary["simulation_set"] = populate_simulation_set(study_dir) except Exception as exc: summary["simulation_set"] = {"error": str(exc)}`. Add a `pbg-populate-simulation-set` console script (mirror the study_outcomes `main`/`--study`/`--all`) OR fold into the existing sync CLI — keep it simple.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(simulation_set): sync runs populate_simulation_set + CLI`

## Task 4: Golden on a real study (tmp copy)
- [ ] **Step 1 (skipif absent):** copy the real `dnaa-2-nucleotide-balance/study.yaml` (has NO simulation_set but rich runs[] + conditions) to a tmp dir; `populate_simulation_set(tmp)`; assert a `simulation_set` block was created with the baseline + variant entries derived from its real `conditions`/`runs`, the seeds/status reflect the real runs, and ALL original comments/authored content are byte-preserved. **NEVER modify v2e-invest — tmp copy only** (verify `v2e-invest` git status clean after).
- [ ] **Step 2: Full suite** `.venv/bin/python -m pytest -q` green. **Step 3: Commit** — `test(simulation_set): real dnaa-2 golden (tmp copy)`

---

## Self-Review
- Goal: auto-fill the often-blank simulation_set from baseline/variants/runs → T1/T2; auto on post-run via sync → T3; proven on real blank study → T4.
- Constraint honored: all logic is plain Python in pbg-superpowers; dashboard unchanged (it already calls sync + renders simulation_set).
- Never-clobber: conservative fill-when-absent + append-only + never-delete; ruamel comment-preserving (the critical lesson). Never fabricate.
- Types: `derive_entries(spec)->list[dict]`; `populate_simulation_set(study_dir)->{added,updated}`; sync adds `simulation_set` key.

## Notes for executor
- `.venv/bin/python -m pytest`. Mirror `study_outcomes.py` (`_MECHANICAL`, `_write_runs_preserving_comments`, `record_runs`, `sync`) closely — same ruamel `YAML(preserve_quotes=True, width=4096)` + `study_io.atomic_write`.
- Read `vivarium-workbench/.../lib/investigations.py:388-416` for the baseline/variant→entry shape to match (so the dashboard renders the persisted entries the same way it renders the projected ones).
- Real study.yamls READ-ONLY; golden uses a tmp copy. study_verify `_check_simulation_set` wants entries' base refs to resolve to real baseline/variant names — derive `base_model`/`name` accordingly.

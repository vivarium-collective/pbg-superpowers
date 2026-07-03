# SP1 — Downstream Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Wire the verified downstream-persistence gaps so a run's verdict/acceptance/runs/param-drift are written to disk automatically. Spec: `docs/specs/2026-06-11-sp1-downstream-persistence-design.md`.

**Architecture:** New deterministic functions in `pbg_superpowers/`; the vivarium-workbench post-run hook calls them. Code-owned slots, fill-absent, ruamel round-trip, best-effort steps in `sync()` (errors captured), idempotent. Reuse existing verdict/acceptance/check logic — no new math.

**Tech Stack:** Python 3.11, ruamel.yaml, pytest. Repos: `pbg-superpowers` (logic + sync), `vivarium-workbench` (the hook call in Task 2).

**Verified (do not re-litigate):** study `gate_evaluator` is ALREADY persisted by `sync()` (study_outcomes.py:184) — do not duplicate. The gaps are investigation-acceptance auto-write, `enforced_params` writer, and on-disk run reconcile.

---

## Task 1: `enforced_params` derivation + population

**Files:** Modify `pbg_superpowers/param_enforcement.py`, `pbg_superpowers/study_outcomes.py`; Test `tests/test_param_enforcement.py`.

- [ ] **Step 1: Write failing tests.**
```python
# tests/test_param_enforcement.py
from pbg_superpowers.param_enforcement import derive_enforced_params, load_enforced_params

def test_derive_enforced_params_baseline_and_variants():
    spec = {"baseline": [{"params": {"a": 1, "b": 2}}],
            "variants": [{"parameter_overrides": {"b": 9, "c": 3}}]}
    assert sorted(derive_enforced_params(spec)) == ["a", "b", "c"]

def test_derive_enforced_params_empty():
    assert derive_enforced_params({}) == []

def test_populate_enforced_params_fills_then_idempotent(tmp_study_dir):
    # tmp_study_dir has a study.yaml with baseline/variant params, no enforced_params
    from pbg_superpowers.param_enforcement import populate_enforced_params
    r1 = populate_enforced_params(tmp_study_dir); assert r1["written"] is True
    enforced = load_enforced_params(_read_study_yaml(tmp_study_dir))
    assert "a" in enforced
    r2 = populate_enforced_params(tmp_study_dir); assert r2["written"] is False  # idempotent
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.** GROUND the exact shape `load_enforced_params` (`param_enforcement.py:~109`) expects (list of names vs dict) and MATCH it. Add `derive_enforced_params(study_spec) -> list[str]` (union of `baseline[].params` keys + `variants[].parameter_overrides` keys, deduped, sorted). Add `populate_enforced_params(study_dir) -> {"written": bool, ...}`: load study.yaml via the existing ruamel helper (`study_io`), if `enforced_params` absent write the derived list (fill-absent; never overwrite an authored value), atomic ruamel save; return written flag.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Wire into `sync()`.** In `study_outcomes.sync()` add a best-effort step calling `populate_enforced_params(study_dir)` (after `record_runs`, pattern-match the existing try/except steps), record into the summary.
- [ ] **Step 6: Commit** — `feat(param-enforcement): derive + populate enforced_params from declared baseline+variant params; wire into sync`

## Task 2: Investigation acceptance auto-write

**Files:** Modify `pbg_superpowers/study_outcomes.py` (or `investigation_status.py`), `vivarium-workbench/vivarium_workbench/server.py`; Test `tests/test_investigation_status.py` + a dashboard test.

- [ ] **Step 1: Failing test (pbg-superpowers).**
```python
def test_sync_investigation_writes_acceptance(tmp_investigation):
    from pbg_superpowers.study_outcomes import sync_investigation
    r = sync_investigation(tmp_investigation)  # inv dir with member studies that have verdicts
    spec = _read_yaml(tmp_investigation / "investigation.yaml")
    assert "computed_acceptance" in (spec.get("executive") or spec)  # match write_investigation_acceptance's slot
    # idempotent + best-effort:
    assert sync_investigation(tmp_investigation)["ok"] is True
    assert sync_investigation(Path("/nonexistent"))["ok"] is False  # captured, not raised
```
- [ ] **Step 2: fail. Step 3: implement** `sync_investigation(inv_dir, workspace=None) -> {"ok": bool, "changed": bool, "error"?: str}` — a thin best-effort wrapper over `investigation_status.write_investigation_acceptance(inv_dir, workspace)`. Match the exact slot `write_investigation_acceptance` writes (confirm: `executive.computed_acceptance` per the spec).
- [ ] **Step 4: pass.**
- [ ] **Step 5: Wire the dashboard post-run hook.** At the `study_outcomes.sync(study_dir)` call sites in `vivarium-workbench/vivarium_workbench/server.py` (~5036/5057/5419 — confirm), after the study sync, resolve the study's parent investigation dir via `WorkspacePaths` (nested `investigations/<inv>/studies/<slug>/`) and, if found, call `sync_investigation(parent_inv_dir)` (best-effort, behind the lazy `pbg_superpowers` import already used there). Add a dashboard test asserting the hook calls it (or a structural test that the call site exists).
- [ ] **Step 6: Commit** (pbg-superpowers) — `feat(investigation): sync_investigation auto-writes computed_acceptance`; then (vivarium-workbench, separate commit/branch) — `feat(server): auto-write investigation acceptance after study sync`

## Task 3: On-disk run reconcile (backfill)

**Files:** Modify `pbg_superpowers/study_outcomes.py`; Test `tests/test_study_outcomes.py`.

- [ ] **Step 1: Failing test.**
```python
def test_reconcile_runs_registers_ondisk_run_absent_from_yaml(tmp_study_with_ondisk_run):
    # a completed run exists on disk (parquet/sqlite) but study.yaml runs[] doesn't list it
    from pbg_superpowers.study_outcomes import sync
    sync(tmp_study_with_ondisk_run)
    runs = _read_study_yaml(tmp_study_with_ondisk_run).get("runs") or []
    assert any(r for r in runs if r["name"] == "ondisk-run-id")
    # present runs untouched + idempotent
    n = len(_read_study_yaml(tmp_study_with_ondisk_run)["runs"]); sync(tmp_study_with_ondisk_run)
    assert len(_read_study_yaml(tmp_study_with_ondisk_run)["runs"]) == n
```
- [ ] **Step 2: fail. Step 3: implement.** GROUND the existing on-disk-run discovery (`backfill_runs.py` / `simulations_index`) and REUSE it. Add `reconcile_runs(study_dir)` (or fold into `record_runs`): discover completed on-disk runs, add any absent from `runs[]` (fill-absent, same mechanical fields `record_runs` writes), idempotent. Ensure it runs as part of `sync()`/`record_runs` (so it's covered by the existing post-run trigger).
- [ ] **Step 4: pass. Step 5: Commit** — `feat(study-outcomes): reconcile on-disk runs into runs[] (auto-backfill) in sync`

## Task 4: Golden + roll_up.py disposition

**Files:** Test `tests/test_sp1_golden.py` (skipif v2e-invest absent); doc note in `roll_up.py`.

- [ ] **Step 1 (skipif `/Users/eranagmon/code/v2e-invest` absent, READ-ONLY → tmp copy):** copy a real investigation + a member study (with runs) to tmp; run `sync(study)` + `sync_investigation(inv)`; assert the study has `enforced_params` populated and the investigation has `computed_acceptance` written. Never modify the real v2e-invest.
- [ ] **Step 2:** Add a module docstring note to `roll_up.py` clarifying it is now the MANUAL/BULK re-persist tool (the common case is auto via `sync()` + the post-run hook); its `write_gate_evaluator` arm intentionally overlaps `sync()`. Do not delete it.
- [ ] **Step 3:** Full suite green (`pbg_superpowers` tests + the touched dashboard tests). **Step 4: Commit** — `test(sp1): v2e-invest downstream-persistence golden + roll_up.py disposition note`

---

## Self-Review
- Coverage: enforced_params writer (T1), investigation acceptance auto-write (T2 + hook), run reconcile (T3), golden + roll_up disposition (T4) — matches the spec's 4 components. Study gate_evaluator NOT touched (already persisted).
- No placeholders: real test code + concrete steps. The two impl-time GROUNDING checks (the `enforced_params` field shape; the `computed_acceptance` slot name) are explicitly flagged to confirm against live code.
- Names: `derive_enforced_params`/`populate_enforced_params`, `sync_investigation`, `reconcile_runs`. Consistent across tasks.

## Notes for the executor
- `.venv/bin/python -m pytest`. Reuse `study_io` (ruamel) for all study.yaml reads/writes; reuse `WorkspacePaths` for layout; reuse `backfill_runs`/`simulations_index` for run discovery; reuse `write_investigation_acceptance`/`check_enforced_params` — do NOT re-implement.
- Best-effort sync steps: capture errors into the summary, never raise (match the existing `sync()` pattern).
- Task 2's dashboard hook is in a SEPARATE repo (vivarium-workbench) — its own branch + commit + PR; the pbg-superpowers logic merges first (or the dashboard lazy-imports the new fn, tolerant if absent).
- Don't modify real v2e-invest; goldens use a tmp copy.

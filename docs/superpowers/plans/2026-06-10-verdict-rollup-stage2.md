# Coded gate/verdict/acceptance roll-up (spine stage #2) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Roll per-test verdicts up into a **study verdict**, and study verdicts up into an **investigation acceptance**, in deterministic code — writing to the dedicated coded slots the schema already has (`pipeline_gate.gate_evaluator.result`; a computed investigation acceptance), **never overwriting the authored `gate_status`/`executive.verdict`**, and flagging divergence. Collapses the three disagreeing inline `tests-passed` re-implementations into one canonical source. Pure pbg-superpowers Python (mirror `study_outcomes`/`simulation_set`/`band_provenance`); the dashboard renders it; no AI.

**Architecture:** (a) `viva_superpowers/study_verdict.py`: `roll_up_verdict(spec) -> {result, blocked_by, evaluated_by}` + `write_gate_evaluator(study_dir) -> bool` (ruamel, parallel coded slot, divergence flag). (b) `viva_superpowers/investigation_status.py`: `roll_up_acceptance(inv_spec, studies_by_name) -> {verdict_status, criteria, unmet}` + `write_investigation_acceptance(inv_dir, workspace) -> bool`. (c) wire `write_gate_evaluator` into `study_outcomes.sync`; an investigation CLI/hook for acceptance. (d) dashboard render of the computed verdict/acceptance + divergence (read-only).

**Tech:** Python 3.11+, ruamel.yaml, pytest. `.venv/bin/python`. Inputs: `study_outcomes.canonical_outcomes(spec)`, `study_status.count_test_outcomes(spec, runs)`.

**Verdict rule (one canonical place):** from the canonical run's per-test outcomes — `failed` if any FAIL; `passed` if `fail==0 and pass>0` (EXACTLY the DAG predicate at `server.py:9561`); `needs_calibration` if any PARTIAL and no FAIL; `blocked`/`not_started` if no run / no pass. `blocked_by` = the failing + pending test names.

---

## File map
- Create: `viva_superpowers/study_verdict.py`, `viva_superpowers/investigation_status.py`.
- Modify: `viva_superpowers/study_outcomes.py` (`sync` also writes the gate evaluator) + `pyproject.toml` (a `pbg-roll-up` CLI / extend sync CLI).
- Modify (dashboard): `vivarium_workbench/server.py` (surface computed verdict/acceptance) + `static/study-detail.js` / investigation render.
- Test: `tests/test_study_verdict.py`, `tests/test_investigation_status.py` (+ dashboard test).

---

## Task 1: `roll_up_verdict` (study, pure)
- [ ] **Step 1: Failing tests** — `roll_up_verdict(spec)` on specs with canonical-run outcomes: all PASS → `{result: passed, blocked_by: []}`; one FAIL → `{result: failed, blocked_by: [that test]}`; a PARTIAL + rest PASS → `{result: needs_calibration, blocked_by: []}`; no runs / no outcomes → `{result: not_started}` (or `blocked` if it has prerequisites). `evaluated_by: code`. Uses `canonical_outcomes(spec)` + the declared test names (behavior_tests + tests).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** mirroring the `_TEST_PASS/_TEST_FAIL` sets in `study_status.count_test_outcomes`; the rule above; `blocked_by` = FAIL + pending test names.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_verdict): roll_up_verdict from canonical per-test outcomes`

## Task 2: `write_gate_evaluator` (parallel coded slot, never clobber authored)
- [ ] **Step 1: Failing tests** (study.yaml from RAW TEXT w/ comments + an authored `gate_status`) — `write_gate_evaluator(study_dir)` writes `pipeline_gate.gate_evaluator: {result, blocked_by, evaluated_by: code, diverges_from_authored: <bool>}` (the parallel coded verdict); the authored `gate_status` and `report.verdict` are NEVER modified; `diverges_from_authored` true when authored `gate_status` (mapped) != computed `result`; comments byte-preserved; idempotent (False on no-op); returns bool.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — ruamel round-trip (mirror `simulation_set._write_simset_preserving_comments`); set only `pipeline_gate.gate_evaluator.{result,blocked_by,evaluated_by,evaluated_at?,diverges_from_authored}` from `roll_up_verdict`; NEVER touch `gate_status`/authored fields; write only if changed. (Use a fixed/None `evaluated_at` or omit — Date is unavailable in this env; the caller may stamp it. Prefer omitting evaluated_at to stay deterministic/idempotent.)
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_verdict): write_gate_evaluator (parallel coded slot, divergence flag)`

## Task 3: `roll_up_acceptance` + write (investigation)
- [ ] **Step 1: Failing tests** — `roll_up_acceptance(inv_spec, studies_by_name)` where `inv_spec.acceptance_criteria = [{study, behavior}]` and `studies_by_name[slug]` is that study's spec: each criterion → the member study's `canonical_outcomes(study)[behavior].result`; aggregate: all PASS → `passing`; any FAIL → `failing`; any pending/not-run → `in-progress`; any PARTIAL (no FAIL) → `passing-with-caveats`. Returns `{verdict_status, criteria: [{study, behavior, result}], unmet: [...]}`. `write_investigation_acceptance(inv_dir, workspace)` writes a parallel `executive.computed_verdict_status` + `computed_acceptance: {criteria, unmet, diverges_from_authored}` (ruamel), NEVER overwriting authored `executive.verdict`/`verdict_status`.
- [ ] **Step 2-4:** implement + pass; mirror the ruamel writer. Read member studies via `WorkspacePaths`/`run_registry`-style study-dir lookup. **Commit** — `feat(investigation_status): roll_up_acceptance + write computed acceptance`

## Task 4: Wire into sync + CLI + dashboard render
- [ ] **Step 1:** `study_outcomes.sync` also calls `study_verdict.write_gate_evaluator` (best-effort, same try/except pattern; `summary["gate"] = {...}`). A `pbg-roll-up` CLI (`--study`/`--all` for gate; `--investigation` for acceptance) mirroring the study_outcomes `main`. Tests.
- [ ] **Step 2:** Dashboard (render only, no AI): surface the computed gate verdict + `diverges_from_authored` on study-detail (mirror the computed-outcomes panel), and the computed investigation acceptance + `unmet[]` on the investigation view. Defensive import. Python data-path test asserting the served data carries the computed verdict/acceptance. (Optional: have the DAG gate `_condition_satisfied`/the badge PREFER `gate_evaluator.result` when present — only if low-risk; else leave the existing read and just render the coded verdict alongside.)
- [ ] **Step 3:** Full suite both repos green. **Commit(s)** — `feat(study_verdict): sync + CLI` / `feat(dashboard): render computed verdict + acceptance divergence`

---

## Self-Review
- Goal: per-test → study verdict (T1/T2) → investigation acceptance (T3), deterministic, parallel coded slots, never overwrite authored (user decision), divergence flagged; collapses the 3 inline tests-passed copies (the `passed` rule == `server.py:9561`). Wired into sync (T4); dashboard renders (T4).
- Constraint: pure pbg-superpowers Python; dashboard renders only; no AI.
- Never-clobber: gate_evaluator/computed_acceptance are NEW parallel slots; authored gate_status/executive.verdict untouched; ruamel comment-preserving; idempotent.
- Types: `roll_up_verdict(spec)->{result,blocked_by,evaluated_by}`; `write_gate_evaluator(study_dir)->bool`; `roll_up_acceptance(inv,studies)->{verdict_status,criteria,unmet}`.

## Notes for executor
- `.venv/bin/python -m pytest`. Mirror `simulation_set._write_simset_preserving_comments` / `study_outcomes` ruamel writers.
- The `passed` predicate MUST equal `vivarium-workbench server.py:_condition_satisfied` `tests-passed` (`counts["fail"]==0 and counts["pass"]>0`) so the gate and the verdict agree.
- Date/time unavailable deterministically — omit `evaluated_at` (or let the caller stamp it); keep writes idempotent.
- Don't modify real v2e-invest; tests use tmp/inline. Real investigation acceptance_criteria example: `v2e-invest/investigations/dnaa-replication/investigation.yaml` (acceptance_criteria ~460).
- Dashboard `main` may be in the `vivarium-workbench-pdmp` worktree; branch off origin/main.

# Study Evaluator (Increment B2, core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A **pure** evaluator that turns a study's behavior tests + a run's data into computed per-test outcomes — `evaluate_study(spec, run_reader) -> {test_name: outcome}` — using a closed `measure`/`pass_if` DSL over `pbg_emitters.RunReader`. **No `study.yaml` writes** (the stamp/reconciliation into study.yaml is a deliberate follow-on, B2b, so code's verdicts can be golden-tested before they touch authored studies).

**Architecture:** `viva_superpowers/study_evaluator.py`. For each behavior test: classify the `measure.kind` as run-data-evaluable or not (non-run-data kinds → `agent` bucket, never guessed); resolve the `path` to a series via `RunReader`; apply the `window`; reduce per the `kind`; apply the `pass_if` op → PASS/FAIL/PARTIAL + `measured_value` + provenance. Anything unresolvable (unknown observable, unsupported window/op, partial data) → `agent`/`needs_rerun` bucket — **never a fabricated PASS**.

**Tech Stack:** Python 3.11+, `pbg_emitters.RunReader` (returns polars DF `[generation,time,abs_time,value]`), polars, numpy; pytest. Spec: `docs/specs/2026-06-09-study-run-outcome-spine-design.md` §5. Operator set grounded in the v2e-invest census (program memory).

**Repo:** `pbg-superpowers`. New dep: `pbg-emitters` (+ its reader extras polars/duckdb) — add to pyproject.

---

## Contract

```python
# viva_superpowers/study_evaluator.py
def evaluate_study(spec: dict, reader: "RunReader") -> dict[str, dict]: ...
def evaluate_test(test: dict, reader: "RunReader") -> dict: ...

# outcome dict (code path):
{ "result": "PASS"|"FAIL"|"PARTIAL", "measured_value": <scalar|list>,
  "evaluated_by": "code", "operator": "<kind>/<op>", "detail": "<short>" }
# bucket path:
{ "evaluated_by": "agent", "reason": "<why not code-evaluable>" }
{ "evaluated_by": "needs_rerun", "reason": "<partial/missing data>" }
```

### Run-data vs agent (the bucket split — from the census)
```python
RUN_DATA_KINDS = {
  "range_check_per_generation", "generation_average", "derived_scalar",
  "per_generation_mass_ratio", "oric_initiations_per_generation",
  "rate_match", "snapshot_window", "count_over_lineage", "periodicity_check", "per_gen",
}
# everything else (model, tooling, methodological, parca, introspection, computational,
# visualization, investigation, biological, single, ...) -> {"evaluated_by":"agent", reason:"non-run-data kind"}
```

### Closed pass_if op set (params in parens)
| op | params | semantics |
|---|---|---|
| `range` / `in_range` | low, high | scalar in [low,high] |
| `in_range_every_generation` / `generation_average_in_range` | low, high | per-gen series: every element in [low,high] |
| `<=` `>=` `<` `>` `==` `!=` `eq` | value | scalar comparator (`eq`≡`==`) |
| `in_set` | set | measured value(s) ⊆ set |
| `cv_below` | cv_threshold | coefficient-of-variation(series) < threshold |
| `median_within_tolerance` | target, tolerance_fraction | |median−target|/|target| ≤ tol |
| `periodic_doubling_every_generation` | tolerance | per-gen (max/min) ratio within tolerance of 2.0, every gen |
| `exactly_one_initiation_per_generation` | — | per-gen initiation count == 1 every gen |
Unsupported op → agent bucket.

### Window vocabulary
`full_lineage_from_gen_0` (all), `from_generation_N` (parse N; gens ≥ N), `every_generation` (per-gen grouping), `peak_of_each_cycle` / `peak_of_each_cycle_from_gen_N` (max value per gen, gens ≥ N), `gen_steady_state` (default = from generation 3; documented heuristic). Unsupported window → agent bucket.

### Path resolution
`measure.path` (or `field`) is a dotted observable (`listeners.mass.cell_mass`) OR a simple arithmetic expression over observables (`a / (b + c)`, `a * 2`). Resolve each observable token via `reader.series(token)`, align by `(generation, abs_time)`, evaluate the arithmetic per row → a derived `[generation, time, abs_time, value]` series. If ANY token raises `KeyError` (unknown observable — incl. bulk-molecule ids like `MONOMER0-160[c]` which the reader doesn't resolve yet) → agent bucket with `reason: "observable <x> not resolvable"`. (Bulk-molecule resolution is a documented follow-on.)

---

## Task 1: Module skeleton + bucket classifier + dep

**Files:** Create `viva_superpowers/study_evaluator.py`; Modify `pyproject.toml`; Test `tests/test_study_evaluator.py`.

- [ ] **Step 1: Failing test**
```python
from viva_superpowers import study_evaluator as se
def test_non_run_data_kind_routes_to_agent():
    out = se.evaluate_test({"name":"t","measure":{"kind":"tooling"},"pass_if":{"op":"eq","value":True}}, reader=None)
    assert out["evaluated_by"] == "agent"
def test_missing_measure_routes_to_agent():
    out = se.evaluate_test({"name":"t"}, reader=None)
    assert out["evaluated_by"] == "agent"
```
- [ ] **Step 2: Run → fail** (`.venv/bin/python -m pytest tests/test_study_evaluator.py -v`)
- [ ] **Step 3: Implement skeleton** — `RUN_DATA_KINDS`, `evaluate_test` early-returning the agent bucket for missing/non-run-data kinds; `evaluate_study` looping tests. Add `pbg-emitters` to `pyproject.toml` `[project.dependencies]` (note: pulls polars/duckdb).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — `feat(study_evaluator): skeleton + bucket classifier; depend on pbg-emitters`

## Task 2: Path/expression resolver over RunReader

**Files:** Modify `study_evaluator.py`; Test `tests/test_study_evaluator.py`.

- [ ] **Step 1: Failing tests** — build a fake reader (a small stub exposing `.series(name)` returning a polars DF and raising `KeyError` for unknown) and assert: single observable resolves to its series; `a / b` resolves to the per-row quotient aligned on `(generation, abs_time)`; an unknown token raises a sentinel the caller maps to the agent bucket.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `_resolve_series(path, reader) -> pl.DataFrame`** — tokenize identifiers (dotted paths and `NAME[c]`-style ids), fetch each via `reader.series`, join on `[generation, abs_time]`, evaluate the arithmetic with a SAFE evaluator (allow only `+ - * / ( )` and the fetched columns — no `eval` of arbitrary code; build a polars expression or use `numpy` over aligned arrays). Raise `ObservableNotFound` on any `KeyError`.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — `feat(study_evaluator): path/expression resolver over RunReader`

## Task 3: Windowing

**Files:** Modify `study_evaluator.py`; Test `tests/test_study_evaluator.py`.

- [ ] **Step 1: Failing tests** — given a 3-gen series, assert each window selects the right rows/aggregation: `full_lineage_from_gen_0` (all), `from_generation_3` (gens≥3), `every_generation` (groups), `peak_of_each_cycle` (max per gen), `gen_steady_state` (gens≥3 default). Unsupported window → `WindowNotSupported`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `_apply_window(series, window) -> WindowResult`** producing either a flat series or a per-generation series (a dict gen→value), per the table above.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — `feat(study_evaluator): window vocabulary`

## Task 4: Measure reduction + pass_if operators

**Files:** Modify `study_evaluator.py`; Test `tests/test_study_evaluator.py`.

- [ ] **Step 1: Failing tests — one per op in the closed set**, with synthetic series (e.g. `in_range_every_generation` low/high over a per-gen series → PASS when all in band, FAIL otherwise; `cv_below`; `median_within_tolerance`; `<=`; `in_set`; `periodic_doubling_every_generation`; `exactly_one_initiation_per_generation` over an oriC 1→2 series). Each asserts `result` and `measured_value`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the kind→reduction and op→predicate functions for the closed set. Wire `evaluate_test`: classify → resolve → window → reduce(kind) → predicate(op) → outcome dict with `measured_value`, `operator`, `detail`. Unsupported kind/op/window or `ObservableNotFound`/`WindowNotSupported` → agent bucket; empty/partial series for a windowed gen → `needs_rerun`. Compute `calibration_anchor.divergence_factor` when an anchor is present.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** — `feat(study_evaluator): measure reductions + pass_if operators`

## Task 5: Golden test against the real dnaa-1 run

**Files:** Test `tests/test_study_evaluator_golden.py`.

- [ ] **Step 1: Write the golden test (skipif the real paths are absent)** — load `behavior_tests`/`tests` from `/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/study.yaml`; open the real hive `.../dnaa-1-expression/parquet-runs/dnaa1-mechA-1.7e-3-7gen/dnaa1_mechA_1p7e-3_7gen` via `RunReader`; run `evaluate_study`. Assert: (a) no exceptions; (b) every outcome is one of the valid shapes; (c) tests whose `path` is a clean resolvable observable + supported kind/op/window are `evaluated_by: code` with a concrete `result` + `measured_value`; (d) tests needing aggregation/bulk/unsupported windows are `evaluated_by: agent` with a reason (never a fabricated PASS). Print the per-test verdict table so the result is inspectable.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_study_evaluator_golden.py -v -s` — confirm it runs against the real hive and the code-evaluated verdicts are sane (spot-check one against the study's authored result, e.g. an in-band check).
- [ ] **Step 3: Run full suite** `.venv/bin/python -m pytest -q` — green.
- [ ] **Step 4: Commit** — `test(study_evaluator): golden evaluation against real dnaa-1 run`

---

## Self-Review
- **Spec coverage (§5):** closed measure/pass_if DSL → Tasks 3-4; resolver via observables → Task 2; buckets code/agent + never-guess → Tasks 1,4; provenance (operator/measured_value) → Task 4; divergence_factor → Task 4. Deferred (documented): pytest bucket, bulk-molecule resolution, study.yaml stamp + trust-reconciliation (B2b), schema enum + migration (B3).
- **Placeholder scan:** operator/kind/window semantics are tabulated; tests carry concrete assertions; golden test names the real paths.
- **Type consistency:** `evaluate_test`/`evaluate_study` return the outcome dicts above uniformly; `_resolve_series -> pl.DataFrame[generation,time,abs_time,value]`; `_apply_window` result fed to reductions consistently.

## Notes for the executor
- `RunReader` is importable in `.venv` (polars+duckdb installed; pbg-emitters editable from the sibling on `feat/run-reader`). Add `pbg-emitters` to pyproject so it's declared.
- Run tests via `.venv/bin/python -m pytest`.
- Keep it PURE — no writes to study.yaml in this increment.
- The real dnaa-1 hive is read-only; never modify v2e-invest.
- Where a real dnaa-1 test needs "aggregated across DnaA forms" (an aggregation the bare path doesn't express) or a bulk-molecule id, routing it to the agent bucket is CORRECT for B2 — note it; the structured `aggregate` selector + bulk resolution come in B3/follow-on.

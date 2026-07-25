# Evaluator via readout resolution (Readout-coord #6 — THE PAYOFF) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Make the study evaluator compute the authored dnaa **vector/bulk** verdicts by resolving measure tokens that aren't scalar observables — bulk ids (`MONOMER0-160[c]`), vector indices (`monomer_counts[3861]`), and readout aggregates — through `RunReader.select`/`aggregate_series` instead of routing them to the agent bucket. This is the payoff of the whole readout-coordination program.

**Architecture:** Extend `viva_superpowers/study_evaluator.py`. Today `_resolve_series(path, reader)` tokenizes the measure expression and resolves EACH token via `reader.series(token)` — bulk ids / vector elements raise → `ObservableNotFound` → agent. Add a fallback: when `reader.series(token)` fails, resolve the token as a structured selector via `RunReader.select` (bracket-id → `bulk_id`; `path[N]` → `literal_index`). Reuse `readout_resolver`'s parsing so the grammar matches. Returns the same `[generation,time,abs_time,value]` shape, so `_eval_expression` + windows + ops work unchanged. Plus the `per_minute` rate window (spec #6).

**Tech:** Python 3.11+; `.venv/bin/python` (has `pbg-emitters[parquet]` = polars/duckdb). Spec: `docs/specs/2026-06-09-readout-coordination-design.md` (#6). Depends on: `study_evaluator` (B2, on main), `readout_resolver` (#3, on main), `RunReader.select`/`aggregate_series` (#2, on main).

**Repo:** pbg-superpowers, branch `feat/evaluator-via-readouts` (off main, set).

---

## File map
- Modify: `viva_superpowers/study_evaluator.py` (`_resolve_series` token fallback; new `per_minute` window in `_validate_window`/`_apply_window`/`_KNOWN_WINDOWS`).
- Test: `tests/test_study_evaluator_via_readouts.py` + a golden in `tests/test_study_evaluator_golden.py` (or a new golden file).

---

## Task 1: token → `RunReader.select` fallback in `_resolve_series`

**Files:** Modify `study_evaluator.py`; Test `tests/test_study_evaluator_via_readouts.py`.

- [ ] **Step 1: Failing test** — build (or write) a SELF-DESCRIBING parquet store with a `bulk` (`bulk__id`/`bulk__count`) and a catalogued listener vector (mirror `tests/test_run_reader_catalog.py`'s synthetic fixture). Then:
  - `_resolve_series("MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])", reader)` returns a `[generation,time,abs_time,value]` series (the fraction), NOT raising — each bulk-id token resolved via `select`.
  - `_resolve_series("listeners.monomer_counts[3]", reader)` resolves via `select(literal_index)`.
  - a genuinely-absent token still raises `ObservableNotFound` (never-guess preserved).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — in `_resolve_series`'s per-token loop, on `reader.series(token)` failure, attempt a selector fallback before raising: if the token is a bracket id (matches `readout_resolver`/`_BRACKET_ID`, e.g. `NAME[c]`) → `reader.select({"type":"bulk_id","value":token,"observable":"bulk"})`; if it matches `<dotted.path>[<int>]` → `reader.select({"type":"literal_index","value":N,"observable":"<dotted.path>"})`. Reuse `readout_resolver` parsing (e.g. its single-target parse / `to_select_dict`) rather than new regex where clean. Only raise `ObservableNotFound` if BOTH series and select fail. The returned DataFrame must have the standard columns so `_eval_expression` works.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_evaluator): resolve bulk-id/literal-index measure tokens via RunReader.select`

## Task 2: `per_minute` rate window

**Files:** Modify `study_evaluator.py`; Test same file.

- [ ] **Step 1: Failing test** — `_apply_window(series, "per_minute_full_lineage")` (name to match the existing window vocab style — check `_KNOWN_WINDOWS`/`_FROM_GEN_RE`) returns a rate series: per-step Δvalue / Δtime scaled to per-minute over the lineage (time is in the series' `abs_time`/`time` units — confirm units; if minutes already, Δvalue/Δtime). Assert exact values on a small hand-built series; `_validate_window` accepts it.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — add the window to `_KNOWN_WINDOWS` (or a regex) + a branch in `_apply_window` computing the rate (diff value / diff time, guard div-by-zero → drop/zero, scale to per-minute based on the time unit). Keep the `[generation,time,abs_time,value]` shape.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_evaluator): per_minute rate window`

## Task 3: readout-name + aggregate evaluation (if clean)

**Files:** Modify `study_evaluator.py`; Test same file.

- [ ] **Step 1: Failing test** — a measure whose `path` is a readout NAME that `resolve_study_readouts(spec)` maps to a readout with `aggregate:{op:sum, over:[id1,id2,id3]}` evaluates via `reader.aggregate_series(observable, "sum", over=[...])`; an unresolved/ambiguous readout → agent (never-guess). (If wiring readout-name lookup into `evaluate_test` proves to need spec plumbing beyond scope, SKIP this task and note it — Tasks 1+2+4 are the payoff; document the deferral.)
- [ ] **Step 2-4:** implement + pass + commit `feat(study_evaluator): evaluate readout-name measures via aggregate_series`. (Optional.)

## Task 4: Golden — the authored dnaa verdict computes by CODE

**Files:** Test (golden, skipif real paths absent).

- [ ] **Step 1:** Using the REAL dnaa-1 parquet hive (`/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/parquet-runs/dnaa1-mechA-1.7e-3-7gen/dnaa1_mechA_1p7e-3_7gen`, bulk self-describing via `bulk__id`, skipif absent), evaluate the real dnaa-2 ATP-fraction test:
  ```python
  test = {"name":"dnaa-atp-fraction","measure":{"kind":"generation_average",
          "path":"MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])"},
          "pass_if":{"op":"in_range","low":0.2,"high":0.5}}  # use the test's REAL op/kind from dnaa-2 study.yaml
  ```
  Assert `evaluate_test(test, reader)["evaluated_by"] == "code"` (was `agent` before #6) with a numeric `measured_value` (a fraction in [0,1]). This proves a real bulk-id expression verdict computes run-only.
- [ ] **Step 2:** A literal-index golden if a self-describing listener-vector run is available; else document the bulk golden suffices (literal_index is unit-tested in Task 1). NEVER modify v2e-invest — read-only.
- [ ] **Step 3: Full suite** `.venv/bin/python -m pytest -q` green. **Step 4: Commit** — `test(study_evaluator): dnaa bulk-expression verdict computes by code (payoff golden)`

---

## Self-Review
- Spec #6: evaluator resolves measure via readout/RunReader (Task 1 = bulk-id + literal-index; Task 3 = aggregate) → computes authored dnaa vector/bulk tests (Task 4 golden); `per_minute` window (Task 2). Never-guess preserved (absent token → ObservableNotFound → agent).
- No placeholders: real dnaa-2 measure string + real hive drive the golden; window math specified.
- Types: `_resolve_series` still returns `[generation,time,abs_time,value]`; fallback uses `RunReader.select` (#2) with `to_select_dict`-shaped dicts (#3).

## Notes for executor
- `.venv/bin/python -m pytest`. RunReader importable (evaluator extra installed).
- Read `study_evaluator.py` (`_resolve_series` ~:214, `_extract_observable_tokens` ~:183, `_validate_window`/`_apply_window` ~:354-410, `_KNOWN_WINDOWS`) + `readout_resolver.py` (`to_select_dict`, the single-target parse) + `pbg_emitters.RunReader.select`/`aggregate_series` signatures before coding.
- Confirm the dnaa-2 test's REAL `pass_if.op`/`measure.kind` from `studies/dnaa-2-nucleotide-balance/study.yaml` (around the `tests:` block) and use them in the golden so it matches a supported op (if the real op isn't supported, the golden still asserts the SERIES/measured_value resolves by code via a supported op like `in_range`).
- Real dnaa paths READ-ONLY; goldens use them read-only or tmp copies.

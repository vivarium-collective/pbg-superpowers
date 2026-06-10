# B2b — Computed-outcomes write-back (parallel block) Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Run the B2 evaluator over a study's runs and stamp the computed verdicts into a **parallel, code-owned `computed_outcomes` block per run** in `study.yaml` — **never touching the hand-authored `outcomes`** — with a per-test `reconcile: agree|divergent|no_authored` flag. Comment-preserving (ruamel), idempotent.

**Architecture:** `pbg_superpowers/study_evaluator.py` gains a write layer: `compute_outcomes(study_dir) -> summary`. For each run in `study.yaml runs[]`, resolve its store, open a `RunReader`, run `evaluate_study(spec, reader)`, and write `run["computed_outcomes"] = {test: outcome}` plus `run["computed_outcomes"]["<test>"]["reconcile"]` derived by comparing `outcome.result` to the authored `run["outcomes"][test].result` (if present). Authored `outcomes` is read-only here. Write via ruamel round-trip (preserve comments). Decision recorded: **parallel block, never overwrite authored** (user choice 2026-06-09).

**Repo:** pbg-superpowers, branch `feat/study-evaluator-b2` (extends the evaluator PR). Depends on RunReader (pbg-emitters, in venv) + `evaluate_study` (B2-core).

---

## Task 1: Store resolution per run

**Files:** Modify `pbg_superpowers/study_evaluator.py`; Test `tests/test_computed_outcomes.py`.

- [ ] **Step 1: Failing test** — given a run dict with `emitter.store` / `run_dir` / `parquet` fields and a workspace root, `_resolve_run_store(run, study_dir, ws_root)` returns the RunReader-openable path (the dir containing `history/` for parquet), or `None` if unresolvable. Test the precedence and the "descend to the experiment dir that holds history/" behavior with a tiny hive.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `_resolve_run_store`** — try in order: `run["emitter"]["store"]`, `run["run_dir"]`, `run["parquet"]`. Resolve relative paths against `study_dir` then `ws_root` then cwd. For a parquet candidate, if the path doesn't directly contain `history/`, glob for the descendant dir that does (the experiment dir) and return it. Return `None` (caller skips → `needs_rerun`/agent, never guess) if nothing resolves.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_evaluator): per-run store resolution`

## Task 2: `compute_outcomes` writes the parallel block (comment-preserving, idempotent)

**Files:** Modify `study_evaluator.py`; Test `tests/test_computed_outcomes.py`.

- [ ] **Step 1: Failing test** — a study.yaml (written as RAW TEXT with comments + an authored `outcomes` block on a run) whose run points at a tiny resolvable store; `compute_outcomes(study_dir)` writes `run["computed_outcomes"]` with per-test `{result, measured_value, evaluated_by, operator, detail, reconcile}`; assert: (a) authored `outcomes` is byte-unchanged; (b) comments preserved; (c) `reconcile` is `agree` when computed==authored, `divergent` when not, `no_authored` when no authored entry; (d) a second `compute_outcomes` is byte-identical (idempotent); (e) returns `{runs_evaluated, tests_code, tests_agent}`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `compute_outcomes(study_dir)`** — load study.yaml (plain + ruamel round-trip for write, mirroring `study_outcomes.record_runs`'s ruamel approach — reuse a shared helper if present, else replicate); for each run: resolve store (Task 1); if unresolved, set `run["computed_outcomes"] = {"_status": "store_unresolved"}` and continue (never fabricate); else `RunReader.open(store)`, `evaluate_study(spec, reader)`, attach `reconcile` per test by comparing to authored `outcomes`, write into `run["computed_outcomes"]`. Only write the file if something changed. NEVER modify `run["outcomes"]`.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(study_evaluator): compute_outcomes writes parallel computed_outcomes block`

## Task 3: CLI + golden proof on real dnaa-1

**Files:** Modify `study_evaluator.py` (add `main`/CLI or extend the sync entrypoint), `pyproject.toml`; Test `tests/test_computed_outcomes_golden.py`.

- [ ] **Step 1:** add a `compute-outcomes` CLI (mirror `pbg-sync-runs`: `--workspace`, `--study`/`--all`). Failing CLI test.
- [ ] **Step 2-4:** implement + pass; add console script.
- [ ] **Step 5 (golden, skipif real paths absent):** copy the real dnaa-1 `study.yaml` to a tmp dir, point its canonical run at the real hive (or run against a tmp copy whose run `parquet:` resolves to `/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/parquet-runs/dnaa1-mechA-1.7e-3-7gen`), run `compute_outcomes`, and assert: a `computed_outcomes` block was written for that run; the real scalar-resolvable tests (if any) are `evaluated_by: code` with `reconcile` set; the authored vector tests are agent-bucketed; the original authored `outcomes` + comments are untouched. **Operate only on the tmp copy — never modify v2e-invest.** Commit — `test+feat(study_evaluator): compute-outcomes CLI + real dnaa-1 golden`

- [ ] **Final:** full suite `.venv/bin/python -m pytest -q` green.

---

## Self-Review
- Spec/decision coverage: parallel `computed_outcomes` block, authored `outcomes` never touched (user choice) → Tasks 2-3; reconcile flag → Task 2; comment-preserving + idempotent → Task 2; never-guess (unresolved store / agent kinds) → Tasks 1-2; CLI trigger → Task 3.
- Deferred: wiring into the post-run hook / `study_outcomes.sync` + the dashboard render of `computed_outcomes` vs `outcomes` (small integration once Increment A merges); B3 aggregate/bulk.
- Types: `compute_outcomes(study_dir)->summary`; `_resolve_run_store(run,study_dir,ws_root)->str|None`; outcome dicts from `evaluate_study` reused verbatim + `reconcile`.

## Notes
- `.venv/bin/python -m pytest`; RunReader importable (polars/duckdb installed).
- Reuse the ruamel comment-preserving write pattern (see Increment A `study_outcomes.record_runs` on branch feat/study-outcome-spine-increment-a; if that code isn't on THIS branch, replicate the ruamel round-trip here and note the convergence for post-merge).
- Real dnaa-1 paths are READ-ONLY — golden test must use a tmp copy.

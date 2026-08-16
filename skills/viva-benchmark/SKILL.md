---
name: viva-benchmark
description: Use when you want to measure the framework's ability to produce models — runs a suite of open-ended study questions through the autonomous model-building loop, scores each with the process-quality rubric, and writes a benchmark report you can diff across framework variants.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <suite> [--variant-label "<tag>"] [--max-iterations N] [--score-only]
---

# /viva-benchmark

Measure how well the framework turns open-ended questions into validated models,
**repeatably across framework variants**. For each item in a suite it scaffolds a
throwaway study, drives the autonomous model-building loop, and scores the result
with a reference-free process-quality rubric — so you can change the audit/skills/
grading, re-run the same suite, and diff the scores.

Spec: `docs/superpowers/specs/2026-08-16-study-automation-benchmark-design.md`.
Preconditions: a workspace + the workbench running (per `/viva-orient`). The
scoring engine (`viva_superpowers.benchmark_score` / `benchmark_run`) is shipped
and AI-free; this skill adds the orchestration + the two LLM rubric axes.

## The suite

A suite is `benchmarks/<suite>/<item>.yaml` (start from the bundled `suite-v1`).
Each item: `{id, question, domain, difficulty, expected_mechanisms, solvable, notes}`.
Include `solvable: false` controls — the loop MUST give up honestly on them; a
"pass" there is a gamed pass the rubric scores `mismatch`.

## Per-item trial (the loop)

For each item, in an **isolated scratch workspace** (so trials don't collide and
the run is disposable/reproducible):
1. **Scaffold** a study from the item's `question` — `/viva-study new` +
   `fill-overview` (or `set-objective` + author the `question:`).
2. **Drive the loop** — `/viva-model-build <study> --autonomous --max-iterations N`.
   Let it run to DONE or GIVE_UP.
3. **Collect + score** (deterministic):
   ```bash
   python - "$STUDY" <<'PY'
   import sys, json
   from viva_superpowers import benchmark_run, paths
   art = benchmark_run.collect_trial_artifacts(paths.workspace_root(), sys.argv[1])
   print(json.dumps(art))   # loop_state + audit_gate + behavior_tests
   PY
   ```
4. **Fill the LLM rubric axes** (only you can judge these — the scorer leaves them
   `ungraded`):
   - **question_comprehension** — did the study's `question`/`purpose.mechanism`
     faithfully scope the item's question and derive the right `expected_mechanisms`?
   - **model_plausibility** — is the built model's mechanism plausible + non-fabricated
     for the question (cited, not invented to force a pass)?
   Grade each `within_tol` / `drift` / `mismatch` with a one-line justification.

## Aggregate + write the report

Combine every trial (deterministic axes from the collector + your two LLM verdicts)
and aggregate:
```bash
python - <<'PY'
import json
from viva_superpowers import benchmark_run
# trials: [{"item": <item>, "artifacts": <collected + llm axes merged>}], variant from capture_variant
variant = benchmark_run.capture_variant(skills_label="${VARIANT_LABEL:-}", rubric_prompt_version="1")
report = benchmark_run.score_suite(trials, suite="${SUITE}", variant=variant)
# write benchmarks/runs/<run-id>/report.json (a run-id you choose — e.g. suite + variant label)
PY
```
To merge your LLM verdicts into a trial, overwrite the `ungraded` `question_comprehension`
/ `model_plausibility` axes in that trial's report before aggregating (or pass the
verdicts through and rebuild the axis via `test_contract.check(..., verdict=...)`).

Write the `benchmark_report/v1` to `benchmarks/runs/<run-id>/report.json`. Print the
aggregate: `pass_rate` (solvable), `honest_giveup_rate` (impossible),
`gamed_pass_rate` (must be ~0 — a rising rate means the loop is gaming), per-axis means.

## Repeatability / variant diff (the point)

`capture_variant` pins the framework identity (`viva_superpowers` version +
`--variant-label` + rubric prompt version). To evaluate a library change: run the
suite, change the framework (audit, skills, grading), **re-run the same suite** with
a new `--variant-label`, and compare the two reports — which axes improved/regressed,
whether `gamed_pass_rate` moved. That is the eval-driven-development signal.

## `--score-only`

Skip scaffold + dispatch; only collect + score studies that were already run (a
fast, AI-free deterministic signal — the LLM axes stay `ungraded`). Useful in CI.

## Red flags — STOP

- A `solvable: false` control that reached a pass → the loop gamed it; do NOT
  average it away — it is the headline failure the benchmark exists to surface.
- Editing a study's locked Tests to make it pass mid-loop → an I1 violation the
  scorer already forces to `loop_outcome: mismatch`; never "help" the loop cheat.

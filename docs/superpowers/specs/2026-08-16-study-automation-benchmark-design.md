# Study-automation benchmark — systematic design

**Status:** design — approved in brainstorming 2026-08-16 (scoring basis + run
harness decided), pending spec review.

**Goal.** Systematically measure the framework's ability to turn an open-ended
study *question* into a validated model — and measure it **repeatably across
framework variants**, so we can do eval-driven development of the loop, the audit,
and the skills. The system under test is the agentic model-building loop
([[project_agentic_model_building_loop]], `/viva-model-build`); this benchmark
grades it.

**Builds on:** the loop (`loop_state`, `test_audit`/`/viva-audit-tests`,
`/viva-model-build`), the graded `/v2` contract, `severity_gate`,
`roll_up_verdict`. Spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`.

**Architecture rule (binding):** plugin owns judgment (AI + deterministic helpers);
workbench renders + persists (one-way dep). The scorer + report live in
`viva_superpowers`; the LLM-judge reasoning lives in a `/viva-*` skill; the display
is a workbench render. No AI in the workbench.

## 1. Motivation

The loop can author its own Tests and iterate a model to pass them — but *is it
any good*? And when we change the audit, the skills, or the grading, does the
framework get better or worse? Today there is no way to answer either. This
benchmark is the measurement instrument: a fixed suite of open-ended questions,
each run through the loop, each scored by a **reference-free process-quality
rubric**, aggregated, and **diffed across framework variants**.

## 2. Scoring basis (decided): reference-free process-quality rubric

These are open-ended questions with no single correct model, so we do NOT score
against a curated answer key. We score the **process** — did the agent do the
right things well — via a rubric whose axes are mostly signals the loop already
emits, plus an LLM-judge for the irreducibly-subjective parts.

## 3. The benchmark item + suite

`benchmarks/<suite>/<item>.yaml`:
```yaml
id: dnaa-initiation-timing
question: "Does DnaA-ATP titration explain the timing of replication initiation?"
domain: replication
difficulty: medium            # easy | medium | hard
expected_mechanisms: [dnaA_atp_titration]   # for objective-coverage scoring (advisory, not an answer key)
solvable: true                # false = an "impossible" control the loop MUST give up on
notes: "..."
```
A **suite** is a versioned directory of items (`benchmarks/suite-v1/`). Items are
data, not code. Include a few `solvable: false` controls (the loop must GIVE_UP
honestly) so the benchmark catches a loop that fabricates passes.

## 4. The run harness (decided): scaffold-per-item → dispatch the loop

For each item, one benchmark **trial**:
1. **Scaffold** a fresh throwaway study from the item's `question` (`/viva-study new`
   / `fill-overview`) in an isolated scratch workspace (so trials don't collide and
   a suite run is reproducible).
2. **Dispatch** `/viva-model-build <study> --autonomous --max-iterations <budget>`
   (the Slice-3 driver; `--autonomous` = no checkpoints).
3. **Collect** the trial artifacts: the study's `loop_state.json` (state, gate,
   iterations, reopen trail, I1-I5 validity), the `test-audit.verdict.json`
   (sufficiency), the run outcomes + `report.json`/`test_diff.json`, and the final
   study.yaml (its Tests + model).
4. **Score** the rubric (§5) over those artifacts.

Trials are independent → a suite run fans out (bounded concurrency). A trial that
errors (scaffold/dispatch crash) scores as `error`, never aborting the suite.

## 5. The rubric (per trial)

Each axis → a graded `/v2` axis (verdict + margin where numeric), so a trial's
score is itself a `report_card_verdict/v2` doc and the whole benchmark reuses the
shipped grading machinery.

| Axis | How scored | Kind |
|---|---|---|
| **question_comprehension** | LLM-judge: did the study's `question`/`purpose.mechanism`/objective faithfully scope the item's question and derive the right `expected_mechanisms`? | LLM |
| **test_sufficiency** | Deterministic — the trial's `/viva-audit-tests` gate (`test_audit.audit_gate` over the locked Tests): `pass`→within_tol, `warn`→drift, `fail`→mismatch. | det |
| **model_plausibility** | Deterministic checks (cited mechanisms present, composite resolves + a run produced outcomes) + LLM-judge (is the mechanism plausible / non-fabricated for the question). | det + LLM |
| **loop_outcome** | Deterministic from `loop_state`: `solvable` item reaching gate `pass` with **zero I1-I5 violations** → within_tol; honest GIVE_UP on a `solvable:false` item → within_tol; an invalid/gamed pass (gate pass but an invariant violation, or a `solvable:false` item that "passed") → **mismatch (hard)**; solvable item that gave up → drift. | det |
| **efficiency** | Deterministic: iterations spent / budget → margin (fewer = better); reopen_count penalized lightly. | det |

`loop_outcome` and `test_sufficiency` are **hard**; the rest soft. A trial's
`overall = worst axis`. An I1-I5 invariant violation anywhere forces
`loop_outcome: mismatch` (the integrity backstop — a gamed pass can never score well).

**Scorer split:** `viva_superpowers/benchmark_score.py` computes all deterministic
axes purely from the collected artifacts (unit-testable, AI-free). The LLM axes
(`question_comprehension`, the plausibility half) are filled by a `/viva-benchmark`
skill that judges against a **versioned rubric prompt** and merges them into the
report. A trial can be scored deterministic-only (LLM axes `ungraded`) for a fast,
AI-free CI signal.

## 6. The framework variant (the repeatability / ablation axis)

A benchmark **run** = (suite × **variant**). The *variant* is a pinned identity of
the framework under test: `{viva_superpowers_rev, workbench_rev, skills_label,
rubric_prompt_version}` — captured automatically at run time (git revs) plus an
optional human label ("audit-v2", "tighter-bands"). Recorded in the report so two
runs are comparable iff their suites match; the **variant-diff** compares per-axis
scores between two runs → which axes improved / regressed when the library changed.
This is the "run again with slightly changed libraries to evaluate the results" ask:
change the framework, re-run the same suite, diff.

## 7. The report + display

`benchmark_report/v1` (written to `benchmarks/runs/<run-id>/report.json`, AI-free
serializer):
```json
{
  "schema": "benchmark_report/v1",
  "suite": "suite-v1", "run_id": "...",
  "variant": {"viva_superpowers_rev": "...", "skills_label": "audit-v2", "rubric_prompt_version": "1"},
  "aggregate": {"n": 12, "mean_overall": 0.71, "by_axis": {"loop_outcome": 0.83, ...},
                "pass_rate": 0.66, "honest_giveup_rate": 1.0, "gamed_pass_rate": 0.0},
  "trials": [{"item": "dnaa-...", "overall": "within_tol", "axes": {...}, "loop_state_ref": "..."}]
}
```
**Display** (workbench render, like the study report cards): a results page —
per-trial rubric **heatmap** (items × axes) + the aggregate — and a **variant-diff
view** (run A vs run B: per-axis Δ, which items flipped). Renders from the report
JSON; degrades in the published static bundle.

## 8. Decomposition for writing-plans (deterministic core first)

1. **`benchmark_score.py`** — the deterministic rubric axes over collected artifacts
   + `build_trial_report(item, artifacts) -> /v2` + `aggregate(trials) -> benchmark_report/v1`.
   Pure, unit-tested. The stable core.
2. **The run harness** — scaffold-per-item + dispatch `/viva-model-build --autonomous`
   + collect artifacts (+ variant capture). Depends on the Slice-3 driver (shipped).
3. **`/viva-benchmark` skill** — runs the harness over a suite, fills the LLM axes,
   writes `benchmark_report/v1`; `--score-only` for deterministic CI.
4. **The display** — workbench results page + variant-diff view.
5. **A starter `suite-v1`** — a handful of items across domains/difficulties incl.
   `solvable:false` controls.

## 9. Validation

- Unit (`tests/test_benchmark_score.py`): the deterministic axes over crafted
  artifacts — a gamed pass (gate pass + an I1 violation) scores `loop_outcome:
  mismatch`; an honest give-up on a `solvable:false` item scores within_tol; a
  `solvable:false` item that "passed" scores mismatch; efficiency margin monotonic
  in iterations; `aggregate` counts (pass_rate / honest_giveup_rate / gamed_pass_rate).
- End-to-end (out of the unit suite): run `suite-v1` once, eyeball the report +
  display; then run it against a deliberately-weakened variant (e.g. audit disabled)
  and confirm the variant-diff shows the expected regression (gamed_pass_rate rises).

## 10. Open decisions (resolve in the plan)

- **Isolated scratch workspace** per suite run (a temp workspace vs a `benchmarks/`
  subtree) — recommend a temp workspace per run so trials + `.pbg/loop` don't collide
  and the run is reproducible/disposable.
- **Concurrency** of trials (each dispatches an autonomous loop — heavy); default
  small (2-4) and configurable.
- **LLM-judge determinism** — the judge prompt is versioned (`rubric_prompt_version`);
  whether to cache/pin judgments for reproducibility of a scored run.
- **Efficiency axis weighting** — how much reopen_count / iterations penalize.
- Skill name `/viva-benchmark` vs `/viva-eval`.

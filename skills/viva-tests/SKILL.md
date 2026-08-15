---
name: viva-tests
description: Use when authoring, enriching, or running a study's Tests — the graded report cards that compile a run's results into a pass/fail verdict AND a signed margin (distance-to-pass) an agent reads to drive iterative model building. Covers scaffolding a TestStep, upgrading bare pass/fail checks into cited graded bands, and running tests to get the report + cross-iteration diff.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: "<author|enrich|run> <study> [name] — see SKILL.md"
---

# /viva-tests

A study's **Test** is the compiled result of grading a finished run against
expectations — the gating verdict AND the **agent-feedback signal** for iterative
model building. This skill authors, enriches, and runs Tests so a model-building
agent (or you) can close the loop: *edit the model → run the study → read the
graded margins and the diff of what the edit moved → pick the next edit.*

A Test is a `viva_superpowers.TestStep` (the renamed `ReportCardStep`; the old name
still imports). Its `build()` emits a `report_card_verdict/v2` document whose axes
are **graded checks**, built with `viva_superpowers.check()`:

```python
from viva_superpowers import TestStep, TestBuilder, check, band, value

class AcetateOverflowTest(TestStep):
    name = "acetate_overflow"
    def build(self, study):
        obs = ...  # measured from the run (see § run: open via ResultsHandle)
        v = (TestBuilder(model_ref=study.study_name)
             .add("Physiology",
                  check("acetate_flux", "Acetate flux", obs,
                        band(2.5, 4.0), units="mM/h", severity="hard",
                        knob=["PtsG.kcat"], cite="Nanchen2006"))
             .build())
        return v, "<html>...</html>"
```

Each axis carries: `verdict` (`within_tol`/`drift`/`mismatch`/`ungraded`), a signed
**`margin`** (≥0 pass; the gradient), `severity` (`hard` gates / `soft` records /
`directional` should-improve), and optional `knob` (which model param moves it) +
`citation` (the band's evidence). `check()` computes `verdict`+`margin` from
`observed` vs an `Expected` — `band(low, high)`, `value(target, op, tol)`, or
`predicate(...)`. **Prefer cited bands over magic numbers.**

## Common prelude
1. `/viva-tests` assumes a workspace + a running workbench. If `.pbg/server/server-info`
   is absent, fail with: "Run `/viva-workbench start` first."
2. Resolve the study dir (nested- and flat-aware): `investigations/<inv>/studies/<slug>/`
   then legacy `studies/<slug>/`. The workbench endpoints resolve the slug server-side.

---

## author `<study> <name>`
Scaffold a new `TestStep` and wire it into the study.

1. Create the subclass in the workspace package's tests module
   (`pbg_<pkg>/tests_cards/<name>.py` or the workspace's existing report-card
   module — follow the workspace convention; grep for existing `TestStep`/
   `ReportCardStep` subclasses). Give it `name = "<name>"`, `applies(study) -> bool`
   (default `True`), and `build(study) -> (verdict_v2_doc, html)`.
2. In `build`, open the run's results via the handle `ResultsStep` produced —
   `study` (a `StudyContext`) for run-free cards, OR read the run's emitted records
   for data-driven ones (`.records()` / `.conn()` DuckDB view named `results`).
   Return a `/v2` doc assembled from `check()` calls via `TestBuilder`.
3. Register the class with the workspace core (the workspace's `build_core()` /
   `core_extensions` already discovers `TestStep` subclasses via `__init_subclass__`;
   just importing the module registers it).
4. Declare it in `study.yaml` under `tests:` as `{name: <name>, kind: report_card,
   card: <name>}` (the workbench merges report_cards + behavioral tests into one
   "Tests" panel). Save via the study's normal edit path (`/viva-study`), never by
   hand-editing if a subcommand exists.

Scaffold each axis as a **graded** `check()` from the start — even a placeholder
`band()` beats a bare `passed: bool`.

## enrich `<study> <test>`
Upgrade an existing Test's axes into stronger agent signal. This is the primary
lever for "add more detail so the model-building agent can improve its design."

1. Read the test's `build()` and the study's observables/analyses (what the run
   actually measures). For each axis that is a bare pass/fail (no `expected`/`margin`),
   propose a graded replacement:
   - an `expected` **band** or `value` grounded in a cited reference — use
     [`/viva-cite-bands`](../viva-cite-bands/SKILL.md) to link the reference and
     write the acceptance band; the same `band(low, high)` + `cite=` lands on the axis.
   - a `severity` (`hard` if it must pass to accept the model; `directional` for a
     quantity that should trend the right way but not gate).
   - a `knob`: the model parameter(s)/wiring most influencing this axis, so the agent
     knows what to turn.
2. Never invent thresholds — derive them from the analyses + cited bands and confirm
   with the human before writing. Bands over magic numbers.
3. Re-run (`run` below) and check the axis now reports a numeric `margin`.

## run `<study>`
Run the study's tests and return the structured feedback signal.

1. Trigger the run through the workbench (the study's Simulate→Evaluate path; the
   run flush writes the cards + the diff). Do NOT re-implement running — use the
   study run endpoint.
2. Read back and report:
   - `<study>/viz/tests/report.json` (or the run's `run_verdict`): overall gate +
     per-card verdicts + counts (`hard_mismatch` is the gate-relevant one).
   - the run's `test_diff.json` (surfaced as `spec["test_diff"]`): per-axis
     `change ∈ {fixed, broke, improved, regressed, new, gone, unchanged}` +
     `margin_delta` — **what the last edit moved**.
3. Present, most-actionable first: **hard `mismatch` axes** (+ their `knob`s), then
   **`directional` axes trending the wrong way** (negative `margin_delta`), then
   fixed/improved wins. This ordered list is the next-edit worklist.

---

## The hardened loop (why this exists)
```
edit model → run study → read report.json + test_diff.json
     ↑                              │
     └── next edit ← failing/low-margin HARD axes (+ knobs) + directional regressions
```
Convergence = gate `pass` (no hard `mismatch`) with hard margins ≥ 0 and directional
margins trending up. The study dir — spec + tests + `report.json` + `test_diff.json`
— is the inspectable, hardened unit an agent iterates against.

## Red flags — STOP
- "I'll assert `passed: bool`" → grade it: `check(..., band(lo, hi))` gives the agent a margin.
- "I'll pick a threshold" → derive it from analyses + a cited band (`/viva-cite-bands`); confirm.
- "I'll hand-write the verdict.json" → emit it from `TestStep.build()` via `check()`/`TestBuilder`; the on-disk `overall` vocabulary is load-bearing.
- "Every axis should gate" → only `hard` axes gate; use `directional` for should-improve quantities so a not-yet-calibrated model isn't falsely failed.

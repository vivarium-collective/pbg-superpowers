# Unified grading vocabulary (Slice 2): one scalar grading grammar behind the study evaluator

**Status:** design — approved in brainstorming 2026-08-16, pending spec review.
**Prior art it builds on:** the shipped Tests-as-Agent-Feedback contract
(`report_card_verdict/v2` via `test_contract.check`/`Expected`; `report.json`;
`severity_gate`) and the grading-move (`card_criteria`/`card_grade` now in
`viva_superpowers`). See `docs/superpowers/specs/2026-08-15-tests-as-agent-feedback-design.md`.
This is "Slice 2" of the modular report-card program: unify the test-type
vocabularies.

## 1. Motivation

Three grading vocabularies coexist in the stack:

1. **`study_evaluator`** (`viva_superpowers/study_evaluator.py`) — the run-data
   evaluator behind `study.yaml` `behavior_tests[]`. A test is `{measure:{kind,
   path|formula, window}, pass_if:{op, ...}}`. It *extracts* a value/series from
   run data (`_resolve_series` + `_apply_window`) and grades it with an op-keyed
   comparator (`_apply_op`), returning **PASS/FAIL** — no margin, no severity, no
   meter.
2. **`card_criteria.grade_axis`** — typed statistical criteria (rel_tol / ttest /
   r2 / pearson / composition / literature / threshold_linear / boolean / status)
   → `within_tol/drift/mismatch`, with a meter but no signed margin.
3. **`test_contract.check`/`Expected`** — the shipped `/v2` agent-facing contract:
   grade a **scalar** `observed` against an `Expected` (band / value+op /
   predicate) → verdict **+ signed margin + severity + meter + citation**.

The costs of the split:
- **Behavior-test results carry no margin/severity.** An agent iterating on a
  model sees only PASS/FAIL from its acceptance criteria — not "how far off" or
  "which generation" — even though the `/v2` contract exists.
- **The authored grammar outruns the implemented one.** Many real
  `behavior_tests` use kinds/ops outside `study_evaluator`'s closed set (e.g.
  `derived_rate_window`, `ratio_at_most`, the `pdmp` `source/observable/reduce` +
  `operator/greater-than` dialect); those silently fall to the "agent" bucket
  (`evaluated_by: "agent"`) and never grade in code. The documented grammar
  (`docs/concepts/expected-behavior-grammar.md`) is a *superset* of what runs.

The **key insight** (from the brainstorm): grading is fundamentally a **scalar**
operation — a signed margin is only well-defined against a single number. But
*everything reduces to a scalar to grade*: r² is a scalar, a p-value is a scalar,
"worst-generation distance-to-band" is a scalar. So the scalar `/v2` grammar can
be **the one grading vocabulary**, if the measurement layer is responsible for
producing the scalar to grade. Measurement (extract → reduce to a number) and
grading (number → verdict+margin) are already cleanly separated inside
`study_evaluator`; this slice formalizes that seam.

## 2. Goals / non-goals

**Goals:**
- **One grading grammar:** `test_contract.check(scalar, Expected) → /v2 axis` is
  the single place a value becomes a verdict+margin+severity. No new grading
  module.
- **`study_evaluator` grades through it:** its scalar/threshold/range/set and
  per-generation comparators are re-expressed as `(reduce → scalar, build
  Expected from pass_if)` and dispatched to `check()`. Every gradeable
  `behavior_test` gains a signed margin + severity **for free**.
- **Additive, non-breaking:** `study.yaml` grammar unchanged; `evaluate_test`
  keeps returning today's `{result, measured_value, evaluated_by, detail}` and
  *adds* the `/v2` axis. PASS/FAIL is projected from the verdict.
- **Close part of the authored↔implemented gap:** the mapping table below covers
  the closed `_SUPPORTED_OPS` set plus the pure authored synonyms that are trivial
  to route (`at_most`→`<=`, `at_least`→`>=`, the `operator: greater-than/less-than`
  spelling). Aliases that need a new *measure* (e.g. `ratio_at_most`, which implies
  a ratio observable) are deferred to a measurement-layer slice.

**Non-goals (out of this slice):**
- **Statistical comparators** (ttest / r2 / pearson / composition / literature)
  stay in `card_criteria.grade_axis`, reachable via the existing
  `report_card_axis` workspace evaluator seam. They already produce a scalar
  (r², r, p, tv); folding them into the same `check()` call is a clean *later*
  slice, not this one.
- **No `study.yaml` migration.** `measure`/`pass_if` stay; no re-authoring.
- **No change to the `{measure_kind: callable(test,reader,ws_root)}` workspace
  registration contract** (`pbg_v2ecoli/evaluators.py` depends on it).
- **No new authored kinds/ops beyond the trivial-alias set.** Genuinely new
  measures (e.g. `xy_correlation`) are a measurement-layer slice of their own.

## 3. The scalar reduction: measurement → number

`evaluate_test` already runs two stages (`viva_superpowers/study_evaluator.py`):
`_resolve_series(path/formula, reader)` → a `[generation, time, abs_time, value]`
frame, then `_apply_window(series, window)` → a windowed tuple `("flat" | "per_gen_all"
| "per_gen_scalar", data)`. Grading is `_apply_op(windowed, pass_if, kind, op)`.

This slice inserts a **reduction** between window and grade: `reduce(windowed,
pass_if) → (scalar, per_gen_detail)`. The reduction is chosen by the op family:

| Windowed shape | Reduction to the graded scalar |
|---|---|
| `flat` (one number) | the number itself |
| `per_gen_scalar` / `per_gen_all`, scalar op | the op's aggregate (mean / median / …) as today |
| `per_gen_*`, **every-generation** op (`in_range_every_generation`, `periodic_doubling_every_generation`, `exactly_one_initiation_per_generation`, `rises_within_cycle`) | the **worst generation's signed distance-to-pass**: `min_g margin_g`, so the scalar is `< 0` iff any generation fails, and its magnitude is how far the worst one is. Per-generation `{gen: value}` kept in `axis.detail`. |
| extremum ops (`max_le/max_lt`, `min_ge/min_gt`) | the extremum (max or min) over the window |
| `cv_below` | the coefficient of variation over the window |

The reduction is **pure** (no reader) — it operates on the already-windowed data,
so it is unit-testable without run data. `measured_value` in the outcome keeps its
current shape (scalar, or `{gen: value}` for per-gen ops) — the reduction's scalar
is used only for grading and is surfaced as the axis `value`.

## 4. The `pass_if → Expected` map

`_apply_op`'s comparison is replaced by: build an `Expected` from `pass_if`, then
`check(reduced_scalar, expected, severity=..., cite=..., units=...)`.

| `pass_if.op` (+ aliases) | `Expected` | notes |
|---|---|---|
| `range`, `in_range`, `in_range_every_generation`, `generation_average_in_range` | `band(low, high)` | per-gen reduces to worst-gen distance (§3) |
| `<=`, `<`, `max_le`, `max_lt`, `at_most`, (`operator: less-than`) | `value(target, op="<="` or `"<")` | extremum reduce for `max_*` |
| `>=`, `>`, `min_ge`, `min_gt`, (`operator: greater-than`) | `value(target, op=">="` or `">")` | extremum reduce for `min_*` |
| `==`, `eq`, `equals` (+ `tolerance`) | `value(target, op="~=", tol=tolerance)` | |
| `!=` | `predicate(x != target)` | no numeric margin (verdict only) |
| `median_within_tolerance` (`target`, `tolerance_fraction`) | `value(target, op="~=", tol=tolerance_fraction)` | reduce = median |
| `cv_below` (`cv_threshold`) | `value(cv_threshold, op="<=")` | reduce = cv |
| `in_set` (`set`/`config`) | `predicate(x ∈ set)` | categorical → verdict only, `margin=None` |
| `periodic_doubling_every_generation` (`tolerance`) | `value(2.0, op="~=", tol=tolerance)` per gen | reduce = worst-gen ratio distance |
| `exactly_one_initiation_per_generation` | `predicate(all gens == 1)` | verdict only |
| `rises_within_cycle` (`min_rise`, `min_fraction`) | `value(min_fraction, op=">=")` | reduce = fraction of cycles that rose |

`severity` defaults to `hard` (a behavior test is an acceptance criterion); a test
may declare `severity: soft|directional` to opt into a non-gating check
(`directional` never emits `mismatch`, matching `check`). `cite` flows from the
test's `cites[]`; `units` from `measure.units`.

**Unknown op or kind** → unchanged behavior: fall to the workspace-evaluator
registry then the **agent bucket** (`evaluated_by: "agent"`). This slice never
*reduces* coverage; it only upgrades the ops already in the closed set (plus the
trivial aliases) from PASS/FAIL to graded `/v2`.

## 5. Output + PASS/FAIL back-projection

`evaluate_test`'s code-bucket outcome gains one field, `axis`, the `/v2` dict from
`check()`:

```json
{
  "result": "FAIL",
  "measured_value": 0.54,
  "evaluated_by": "code",
  "operator": "derived/in_range",
  "detail": "dnaa_atp_fraction=0.54 below band [0.6, 0.8]",
  "axis": {
    "id": "...", "label": "...", "verdict": "mismatch",
    "value": 0.54, "margin": -0.06, "severity": "hard",
    "meter": 0.35, "expected": {"kind": "band", "low": 0.6, "high": 0.8},
    "citation": "Kurokawa 1999", "units": "fraction",
    "detail": {"per_generation": {"0": 0.55, "1": 0.53}}
  }
}
```

`result` is **projected** from `axis.verdict` by the existing map:
`within_tol→PASS`, `mismatch→FAIL`, `drift→PASS` (+ a `caveat`), `ungraded→SKIP`.
This is exactly `behavior_test_card`'s current rollup direction (verdict → status),
inverted — so the PASS/FAIL every downstream consumer reads is unchanged in
meaning, now *derived from* the graded verdict rather than computed separately.

Consumers, untouched:
- `auto_evaluate` writes `runs[].outcomes[name]` — now each carries `axis` too
  (additive; the pill still reads `result`).
- `study_status.bucket_tests` / `roll_up_verdict` read `result` (unchanged).
- `behavior_test_card.build_behavior_tests_verdict` reads `result` +
  `measured_value` (unchanged); it MAY additionally read `axis.margin` to render
  the margin bar the SPA/report already show for report-card axes — a small,
  optional follow-on, not required for this slice.
- `finding_observations` / `band_provenance` read `pass_if.{low,high,threshold}`
  (unchanged — the grammar is intact).

## 6. Architecture / files

New/changed in `viva_superpowers`:

| File | Change |
|---|---|
| `study_evaluator.py` | Insert `_reduce_windowed(windowed, pass_if, op) -> (scalar, detail)` and `_expected_from_pass_if(pass_if, op) -> Expected | None`. `_apply_op` (or a new `_grade_scalar`) builds the `Expected`, calls `test_contract.check`, projects to PASS/FAIL, attaches `axis`. Unknown op/kind path unchanged. |
| `test_contract.py` | No new grammar. Possibly expose a tiny helper `verdict_to_result(verdict) -> "PASS"|"FAIL"|"SKIP"` used by both `study_evaluator` and `behavior_test_card` so the projection lives in one place. |
| `docs/concepts/expected-behavior-grammar.md` | Add a column: which ops now grade to a `/v2` margin vs remain agent-bucket. |

`card_criteria` / `card_grade` — **unchanged** (statistical battery stays behind
the seam).

## 7. Determinism, errors, back-compat

- **Determinism:** grading is pure over the reduced scalar; no timestamps enter
  `axis` (margins/verdicts are content, safe to commit in `verdict.json`).
- **Errors:** a reduction or `check` that raises is caught and the test falls to
  the **agent** bucket with a reason (never aborts `evaluate_study`) — the same
  defensive posture as today's unknown-op path.
- **NaN/inf:** `check` already returns `ungraded` + `margin=None` for a
  non-finite observed (its `allow_nan=False` guard), so a degenerate measurement
  is `SKIP`, not a crash.
- **Back-compat contract:** `result` spellings, `evaluated_by` buckets,
  `measured_value` shape, `pass_if` band shape, and the `{measure_kind: callable}`
  registration are all preserved. The only additive change to any consumer's
  input is the new `axis` key, which old readers ignore.

## 8. Testing plan (TDD)

Unit (pure, no run data):
- `_expected_from_pass_if`: every row of §4 maps to the right `Expected` (band/
  value/predicate + op/tol); unknown op → `None`.
- `_reduce_windowed`: `flat` passthrough; per-gen every-generation → worst-gen
  signed distance (a failing middle generation drives the scalar negative);
  `max_le`→max, `min_ge`→min, `cv_below`→cv.
- End-to-end `evaluate_test` over a synthetic `RunReader`: a band test yields
  `axis.margin` with the right sign; `result` still PASS/FAIL; `in_set` yields a
  categorical axis (`margin=None`); an unknown op still lands `evaluated_by:
  "agent"`.
- Projection: `verdict_to_result` for all four verdicts.
- Regression: the existing `test_study_evaluator*` / `test_computed_outcomes*` /
  `test_evaluator_structural_ops` suites keep passing (result/measured_value
  unchanged).

Cross-repo: `vivarium-workbench` `test_behavior_test_card` and
`test_plugin_import_allowlist` (if `study_evaluator` gains a `test_contract`
import, confirm it's already allowlisted — it is a `viva_superpowers` intra-import,
not a workbench→viva_superpowers surface).

## 9. Decisions resolved / open

**Resolved (brainstorm):**
- Scalar model (Approach A): `check`/`Expected` is the one grammar; measurement
  reduces to the scalar. Not a new `test_types` registry.
- Keep the `study.yaml` grammar; unify the engine only.
- Statistical comparators out of scope (existing seam).

**Open (resolve in the plan):**
- Whether `behavior_test_card` renders `axis.margin` now or in a follow-on
  (recommend follow-on — keep this slice to the evaluator).
- Exact home of `verdict_to_result` (test_contract vs test_vocab — likely
  `test_vocab`, which already owns the verdict↔agent/display maps).
- Whether the trivial authored aliases (`at_most`, `operator/greater-than`,
  `ratio_at_most`) are in this slice or explicitly deferred — recommend include
  only the pure synonyms (`at_most`→`<=`, `operator:*`→op), defer `ratio_at_most`
  (needs a ratio measure).

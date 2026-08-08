# Unified Behavior-Tests Report Card

Status: **proposed** · 2026-08-08 · closes viva-superpowers#98 (grammar hardening) and the "Tests vs Report Cards are two systems" fragmentation.

## Problem

Grading a study today spans **three parallel surfaces and two evaluators**:

| Surface | Field | Evaluator | Reach | Studies (v2ecoli) |
|---|---|---|---|---|
| Tests (calibration ladder) | `behavior_tests[].pass_if` | plugin `study_evaluator.py` (closed ops, offline) | **gates CI** (`study_audit --gate`, `--no-install-package vivarium-workbench`) | 30/37 |
| Tests (pytest grammar) | `behavior_tests[].expect` | workbench `expected_behavior.py` (`(given,measure,expect)`) | needs the workbench | 7/37 |
| Report Cards | `report_card_axis` evaluator + promoted `report_card` HTML artifacts | workspace evaluators + `study_audit` verdict check | mixed | — |

So the same conceptual thing — "did the study meet its acceptance criteria?" — is authored two different ways (`pass_if` vs `expect`), evaluated by two different engines, and surfaced separately from the Report Cards that also grade the study. The grammar **doc** documents the minority (`expect`) grammar. On top of this, the assertion grammar **can't express** two common criteria (viva-superpowers#98):

1. **Config-selection** — "the active kLa correlation equals the *configured* geometry"; "the emitted coupling interval equals the *configured* value". No op reads a config field; no categorical `equals`.
2. **Cross-run** — "the dissolved-O₂ trajectory delta is below tolerance under interval halving". Every measure reads exactly one run.

## Target model — one engine, one grammar, surfaced as the default Report Card

**Decisions (agreed):**

1. **Consolidate on the plugin `study_evaluator` (`pass_if`) as the single assertion engine.** It is load-bearing (30/37), offline, and gates CI, and the dependency direction is one-way (workbench → plugin, enforced by `test_no_workbench_import`), so the *plugin* must own evaluation; the workbench renders its outcomes. The workbench `expect`/`expected_behavior.py` grammar folds into `pass_if` (port its 4 unique ops, migrate the 7 studies) and becomes a deprecation shim.

2. **A behavior-test suite *is* a kind of Report Card** — "Report Card" is the umbrella unit shown under Report Cards. The **Behavior-Tests card is the default instance that every study gets automatically.** It renders like any card but additionally carries the "important function": the machine-checked `pass_if` assertions that grade and gate the study. Other report cards (rendered viz/analysis artifacts) are additional instances of the same unit; a study's `report_card_axis` scores *derive from* the behavior-test outcomes rather than re-grading independently.

```
Report Card (umbrella)
├── Behavior-Tests card   ← DEFAULT, every study; renders pass/fail + evidence AND evaluates (gates)
├── <analysis>.html card  ← optional, promoted artifact
└── …
```

## Grammar hardening (viva-superpowers#98)

All additions are backward-compatible (new optional readout kinds / ops / `given` keys; existing entries untouched) and `status: stub`-friendly.

### A. Config-selection

Config source is the run's **declared params from the study's condition block** (`conditions.baseline.params`, a variant's `params` merged over baseline) — deterministic and backend-independent, so no per-emitter config extraction and no `RunReader` change.

```yaml
# read a configured field directly (categorical)
- name: kla-correlation-is-configured
  measure: {kind: config_value, path: "geometry.kla_correlation"}
  pass_if: {op: equals, value: "wells-riley"}

# assert an emitted observable equals the CONFIGURED value
- name: coupling-interval-matches-config
  measure: {readout: emitted_coupling_interval}   # observable from the run
  pass_if: {op: equals, config: "coupling.interval_s", tolerance_fraction: 0.01}
```

- New readout kind **`config_value`** — resolves a dotted path in the run's declared params to a scalar.
- New op **`equals`** — exact for strings/categoricals; numeric with optional `tolerance` / `tolerance_fraction`. Its expected side is a literal `value:` **or** a `config:` reference (dotted config path). `in_set` gains the same `config:`-reference option.

### B. Cross-run

```yaml
# "dissolved-O2 trajectory delta < tol under interval halving"
- name: do-converges-under-interval-halving
  given: {run: variant, variant: interval-half, compare_to: {run: baseline}}
  measure:
    kind: run_delta
    of: {readout: dissolved_o2}     # inner readout, applied to BOTH runs
    align: time                     # interpolate onto a shared time grid
    metric: max_abs_diff            # | rmse | final_abs_diff | mean_abs_diff
  pass_if: {op: "<", value: 0.05}
```

- New `given.compare_to` names the second run.
- New readout kind **`run_delta`** — applies an inner readout to both runs, aligns by time, reduces to a scalar distance. Plumbing exists at the fixture layer (`baseline_history_for` / `variant_history_for`); the plugin `RunReader`/evaluator gains a "load compare run" capability.

## Work plan (staged; each independently shippable)

| Stage | Repo | Change | Delivers |
|---|---|---|---|
| **0. Spec + doc** | viva-superpowers | This doc; rewrite `expected-behavior-grammar.md` around `pass_if` (canonical), documenting the full plugin op/window set | The contract |
| **1. Config-selection** | viva-superpowers | `config_value` readout + `equals`/`in_set` with `config:`-ref + tolerance in `study_evaluator`; plumb declared params into `evaluate_test` | #98 (A) |
| **2. Cross-run** | viva-superpowers | `given.compare_to` + `run_delta` + time-alignment | #98 (B) |
| **3. Default Report Card** | vivarium-workbench | Every study renders a **Behavior-Tests report card** under Report Cards from `study_evaluator` outcomes; `report_card_axis` derives from those outcomes | Unification |
| **4. Migrate + retire** | both | Port the 7 `expect` studies + 4 unique ops into `pass_if`; deprecate `expected_behavior.py` | Single engine |

Stages 0–2 are pure plugin (offline, CI-gated, no workbench import) and deliver the #98 hardening. Stages 3–4 are the Report-Card unification.

## Backward compatibility

- Existing `pass_if` entries unchanged; new kinds/ops are additive.
- v3 `expect` entries keep working until Stage 4 migrates them; the workbench evaluator stays as a shim during the transition.
- `study_audit --gate` continues to run offline with no workbench dependency (the new readouts/ops live entirely in the plugin evaluator).

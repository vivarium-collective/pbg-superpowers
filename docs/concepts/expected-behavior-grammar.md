# behavior_tests Grammar

The `behavior_tests:` field in `study.yaml` encodes each scientific
prediction as a machine-readable **(given, measure, expect)** triple, paired
with a one-sentence English description that the dashboard renders on the
Overview tab.

> **Field rename (Pass 7).** Section 6 of the canonical 8-section `study.yaml`
> is `behavior_tests:`. The legacy v3 name was `expected_behavior:` (renamed
> because `tests:` is reserved in dashboard v4; see
> [vivarium-workbench-model.md § v4 reserved fields](vivarium-workbench-model.md#v4-reserved-fields)).
> The grammar below applies unchanged under either field name; v3 specs using
> `expected_behavior:` are auto-migrated on read.

Adding a new behavioral test is a YAML edit only — no new test code required.

> **Canonical engine: `pass_if` (`viva_superpowers.study_evaluator`).** There is
> **one** assertion engine — the plugin's `study_evaluator`, which grades
> `behavior_tests[].pass_if`, runs offline, and gates `study_audit`. It is what
> `auto_evaluate` / `compute_outcomes` / the Tests tab / the default Behavior-Tests
> report card all use.
>
> The `(given, measure, **expect**)` form documented below is the **legacy
> workbench grammar**. Its evaluator (`vivarium_workbench.lib.expected_behavior`)
> has been **removed** (workbench #757 — a dead module with zero live consumers).
> **Author new tests with `pass_if`** — see the **Config-selection** and **Cross-run measures**
> sections below for the current grammar; the `expect` sections remain only to
> explain existing v3 entries.

---

## Full entry shape

```yaml
expected_behavior:
- name: <stable-slug>             # required; kebab-case; used as pytest node ID
  en: "<one-sentence English>"    # required; shown in Overview tab
  given:                          # optional; defaults to {run: baseline, window: full}
    run: baseline | variant
    variant: <variant-name>       # required when run == variant
    window: full | second_half | post_initiation_10min
  measure:                        # required; what to compute from history
    kind: <measure-kind>
    # ...kind-specific args (see Measure primitives below)
    reduce: <reduce-mode>         # optional; default: series
  expect:                         # required; assertion on the reduced value
    op: <expect-op>
    # ...op-specific args (see Expect operators below)
  status: implemented | stub | gated  # optional; default: implemented
  requires:                       # optional; cross-references for stubs / gated
    - gap: <gap-id>
    - listener: <listener-id>
    - variant_hook: <hook-id>
  notes: "<xfail reason>"         # optional; shown when status == stub
```

---

## given

| Key | Values | Meaning |
|---|---|---|
| `run` | `baseline` \| `variant` | Which run history to load. |
| `variant` | any variant name | Required when `run: variant`. |
| `window` | `full` | The complete history (default). |
| `window` | `second_half` | Steps from the midpoint onward; useful for steady-state assertions. |
| `window` | `post_initiation_10min` | ±10 min around the first replication-initiation event. (Stub until dnaa-04 lands the initiation-event detector.) |

---

## Measure primitives

All primitives live in `vivarium_workbench.lib.expected_behavior`.
State accessors always look inside the **first agent** found under `state.agents.*`.

### bulk_count

```yaml
measure:
  kind: bulk_count
  id: "MONOMER0-160[c]"        # bulk species ID
  reduce: median                # optional
```

Looks up a species by ID in the bulk array (`{id: [...], count: [...]}` or
list of `(id, count)` pairs). Returns `None` on miss.

### listener_path

```yaml
measure:
  kind: listener_path
  path: "listeners.mass.cell_volume"   # dotted path inside first agent
  reduce: series
```

Walks a dotted path; returns the raw value at each timestep.

### listener_sum

```yaml
measure:
  kind: listener_sum
  path: "listeners.rnap_data.rna_init_event"
  reduce: series
```

Like `listener_path` but sums list-valued outputs (e.g. per-TU event arrays).

### xy_correlation

```yaml
measure:
  kind: xy_correlation
  x: {kind: listener_sum, path: "listeners.rna_synth_prob.n_actual_bound"}
  y: {kind: listener_sum, path: "listeners.rnap_data.rna_init_event"}
```

Paired measure for Pearson tests. `x` and `y` are sub-measures using any
non-xy kind. No `reduce` step — the raw series pair is passed directly to
`pearson_below` / `pearson_above`.

### event_count *(new primitive)*

```yaml
measure:
  kind: event_count
  predicate:
    observable: "listeners.replication.initiation_events"
    op: ">"      # == | > | >= | < | <=
    value: 0
```

Counts the number of timesteps in the (windowed) history where *predicate*
is True. Predicate resolves via `listener_value` first, then `bulk_count` as
fallback.

Returns a single scalar — no `reduce` step needed (though one can be applied).
Useful for asserting that a discrete event occurs (or doesn't occur) a
specific number of times per cell cycle.

### pre_post_event *(new primitive)*

Used with `reduce: pre_post_event_ratio`. Slices the history around the first
timestep matching `event_predicate`, then computes the mean of the same
series kind before vs. after the event.

```yaml
measure:
  kind: listener_sum
  path: "listeners.rnap_data.rna_init_event"
  reduce: pre_post_event_ratio
  event_predicate:
    observable: "listeners.replication.initiation_events"
    op: ">"
    value: 0
  before_min: 10.0   # minutes before event
  after_min: 10.0    # minutes after event
```

The reduced value is `{pre_mean, post_mean, ratio: post_mean/pre_mean}`.
Use with `expect.op: ratio_at_least` or `ratio_at_most`.

### concentration *(new primitive)*

```yaml
measure:
  kind: concentration
  molecule: "MONOMER0-160[c]"
  volume_path: "listeners.mass.cell_volume"
  reduce: median
```

Derived measure: `bulk_count(molecule) / volume(volume_path)` at each
timestep. Closes the gap-1 measurement (DnaA in µM) without requiring a
custom listener Step. Returns `None` on any access miss.

---

## Reduce modes

| Mode | Input → Output | Use case |
|---|---|---|
| `series` | list → list (default) | CV, monotonicity, Pearson tests |
| `median` | list → scalar | Robust steady-state value |
| `mean` | list → scalar | Mean of a series |
| `first_and_last` | list → `{first, last}` | Ratio tests (did it go up or down?) |
| `pre_post_event_ratio` | list → `{pre_mean, post_mean, ratio}` | Gene-dosage / perturbation tests |
| `top_quartile_vs_bottom_quartile` | list → `{q1, q3}` | Spread tests |

---

## Expect operators

| op | Arguments | Assertion |
|---|---|---|
| `in_range` | `low`, `high` | `low ≤ value ≤ high` |
| `rolling_cv_below` | `threshold`, `window_steps` (default 5) | max rolling CV < threshold |
| `ratio_at_most` | `ratio` | `last/first ≤ ratio` (from `first_and_last`) |
| `ratio_at_least` | `ratio` | `last/first ≥ ratio` (from `first_and_last` or `pre_post_event_ratio`) |
| `monotonic_decreasing` | `allow_rebound_pct` (default 0) | series is non-increasing, allowing small rebounds |
| `pearson_below` | `threshold` | Pearson r < threshold (from `xy_correlation`) |
| `pearson_above` | `threshold` | Pearson r > threshold (from `xy_correlation`) |
| `pre_post_event_ratio` | `ratio`, `direction` (`at_least` \| `at_most`) | post/pre ratio comparison (from `pre_post_event_ratio` reduce) |

---

### Graded feedback (report_card_verdict/v2)

Ops in the closed set now grade to a **signed margin + severity** (a `/v2` axis
attached to the outcome as `axis`), not just PASS/FAIL — an agent sees *how far*
a test is from passing. Band + comparator + tolerance ops (`in_range`, `<=`,
`>=`, `==`, `max_le`, `min_ge`, `cv_below`, `median_within_tolerance`,
`periodic_doubling_every_generation`, `rises_within_cycle`) carry a numeric
margin; categorical ops (`in_set`, `!=`, `exactly_one_initiation_per_generation`)
carry a verdict only (`margin: null`). Per-generation ops report the **worst
generation's** margin, with the per-generation breakdown under `axis.detail`.

Ops/kinds outside the closed set (e.g. `ratio_at_most`, `xy_correlation`) still
fall to the agent bucket and carry no `axis` — implementing them is a later
(measurement-layer) slice.

---

## requires vocabulary

| Key | Meaning |
|---|---|
| `gap: <id>` | Depends on a gap listed in `study.yaml.gaps`. |
| `listener: <name>` | Depends on a listener observable that may not exist yet. |
| `variant_hook: <name>` | Depends on a composite parameter hook that may not be wired yet. |

When `status: stub` or `status: gated`, the pytest runner marks the test
`xfail` and includes the `requires` list in the reason string.

---

## status semantics

| status | Pytest behavior |
|---|---|
| `implemented` | Test runs; skips cleanly if no runs.db yet. |
| `stub` | `xfail` — expected to fail until the upstream gap closes. |
| `gated` | `xfail` — gated on a `requires` item being delivered. |

---

## Worked example

**Study:** `dnaa-01-expression-dynamics`
**Finding:** DnaA synthesis is autorepressed — when DnaA is highly bound
to the dnaA promoter, transcription initiation events are low.

**English sentence (en):**
> "When DnaA is highly bound to its promoter targets, dnaA transcription init events are low (autorepression; Pearson r < -0.3)."

**How the sentence maps to the structured triple:**

```yaml
- name: coarse-autorepression-negative-correlation
  en: "When DnaA is highly bound to its promoter targets, dnaA transcription
       init events are low (autorepression; Pearson r < -0.3)."
  given:
    run: baseline
    window: second_half     # measure in steady state, not during warm-up
  measure:
    kind: xy_correlation
    x:
      kind: listener_sum    # sum of n_actual_bound array across all DnaA TUs
      path: "listeners.rna_synth_prob.n_actual_bound"
    y:
      kind: listener_sum    # sum of rna_init_event array
      path: "listeners.rnap_data.rna_init_event"
  expect:
    op: pearson_below
    threshold: -0.3         # r < -0.3 confirms negative correlation
  status: implemented
```

Reading it:
- **given** — run the assertion on the baseline history, looking only at the
  second half of the simulation (steady state).
- **measure** — extract two series: DnaA-bound count vs. transcription-init
  events (both summed across their respective arrays). No reduce step — the
  raw paired series go directly to the Pearson test.
- **expect** — assert that the Pearson r between the two series is < -0.3,
  confirming a negative correlation (autorepression signal).

The evaluator calls `evaluate(entry, history)`, which:
1. Slices `history` to `second_half`.
2. Extracts the `x` and `y` series via `listener_sum`.
3. Computes Pearson r between them.
4. Returns `EvaluationResult(passed = r < -0.3, message = "r=... expected < -0.3")`.

---

## Config-selection (`pass_if` grammar) — #98

The plugin evaluator (`viva_superpowers.study_evaluator`, the closed-op `pass_if`
grammar that gates `study_audit`) can assert against a run's **declared config**,
not just its run-data series. The config source is the run's params from the
study's condition block (`conditions.baseline.params`, a variant's `params`
merged over baseline) — deterministic and backend-independent.

**`config_value` measure** — read a declared param (scalar, incl. categorical):

```yaml
- name: kla-correlation-is-configured
  measure: {kind: config_value, path: "geometry.kla_correlation"}
  pass_if: {op: equals, value: "wells-riley"}
```

**`equals` op + `config:` reference** — the expected side may be a literal
`value:` or a `config:` path into the declared params, so an emitted observable
can be asserted equal to the *configured* value:

```yaml
- name: coupling-interval-matches-config
  measure: {kind: range_check_per_generation, path: "obs.coupling_interval", window: full_lineage_from_gen_0}
  pass_if: {op: equals, config: "coupling.interval_s", tolerance_fraction: 0.01}
```

`equals` is exact for categoricals and numeric-with-tolerance (`tolerance` or
`tolerance_fraction`). `in_set` likewise accepts a `config:`-referenced list.

> This is the first slice of the unified assertion model; see
> `docs/superpowers/specs/2026-08-08-unified-behavior-tests-report-card.md` for
> the full plan (cross-run measures, and behavior tests as the default Report
> Card every study gets).

## Cross-run measures (`run_delta`) — #98

Compare the same readout across **two** runs and assert on the scalar distance —
e.g. "the dissolved-O₂ trajectory converges under interval halving":

```yaml
- name: do-converges-under-interval-halving
  given: {run: variant, variant: interval-half, compare_to: {run: baseline}}
  measure:
    kind: run_delta
    of: {readout: dissolved_o2}     # inner readout, applied to BOTH runs
    align: time                     # interpolate onto a shared abs_time grid (or `index`)
    metric: max_abs_diff            # | mean_abs_diff | final_abs_diff | rmse
  pass_if: {op: "<", value: 0.05}
```

- `given.compare_to` names the second run (same selector shape as `given`).
- `run_delta` applies `of` to the primary run (`given`, defaulting to the run
  under evaluation) and the compare run, aligns them, and reduces to a scalar.
- The evaluator resolves the compare run through a **`run_opener`** callback
  (`evaluate_study(spec, reader, run_opener=…)`); without one, `run_delta` tests
  report `needs_rerun` rather than fabricating a verdict.
- `compute_outcomes` **auto-builds** that opener from the study's `runs[]` and
  evaluates each `run_delta` test **once** (study-level), attaching the outcome to
  its primary run's `computed_outcomes`. Run-selection convention: `{run: baseline}`
  → the `canonical: true` run (else the first with no `variant`); `{run: variant,
  variant: X}` → the run whose `variant` or `name` is `X`.

## Evaluator location

**Canonical:** `viva_superpowers/study_evaluator.py` (the plugin) — the single
`pass_if` engine that grades `behavior_tests`, offline and CI-gating.

**Legacy (removed):** `vivarium_workbench/lib/expected_behavior.py` — the old
`(given, measure, expect)` pytest evaluator — has been **deleted** (workbench
#757; it had zero live consumers, since auto_evaluate / compute_outcomes / the
Tests tab all use the plugin engine). Do not build new work against the `expect`
form. Per-study `tests/_behaviors.py` files in v2ecoli were the original prototype.

## See also

- `docs/concepts/vivarium-workbench-model.md` — overall dashboard architecture.
- `docs/concepts/process-bigraph-glossary.md` — framework terminology.

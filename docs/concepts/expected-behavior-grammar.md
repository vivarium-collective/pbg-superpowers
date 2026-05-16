# behavior_tests Grammar

The `behavior_tests:` field in `study.yaml` encodes each scientific
prediction as a machine-readable **(given, measure, expect)** triple, paired
with a one-sentence English description that the dashboard renders on the
Overview tab.

> **Field rename (Pass 7).** Section 6 of the canonical 8-section `study.yaml`
> is `behavior_tests:`. The legacy v3 name was `expected_behavior:` (renamed
> because `tests:` is reserved in dashboard v4; see
> [vivarium-dashboard-model.md § v4 reserved fields](vivarium-dashboard-model.md#v4-reserved-fields)).
> The grammar below applies unchanged under either field name; v3 specs using
> `expected_behavior:` are auto-migrated on read.

Adding a new behavioral test is a YAML edit only — no new test code required.
The evaluator (`vivarium_dashboard.lib.expected_behavior.evaluate()`) turns
every entry into a deterministic pytest assertion.

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

All primitives live in `vivarium_dashboard.lib.expected_behavior`.
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

## Evaluator location

`vivarium_dashboard/lib/expected_behavior.py` — canonical upstream evaluator.
Per-study `tests/_behaviors.py` files in v2ecoli were the original prototype;
new workspaces should import from the dashboard package instead.

## See also

- `docs/concepts/vivarium-dashboard-model.md` — overall dashboard architecture.
- `docs/concepts/process-bigraph-glossary.md` — framework terminology.

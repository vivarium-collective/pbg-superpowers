# Contributing — study YAML field guide (for humans + AIs)

This is the schema reference for `studies/<slug>/study.yaml` files —
what each section drives in the dashboard, when to fill it, and how the
report linter checks it. AI agents writing new investigations should
consult this before scaffolding studies so the resulting cards aren't
half-blank.

> **TL;DR**: the dashboard renders study cards from MANY fields. If you
> leave a field empty, the corresponding tab/panel in the study-detail
> view is blank. The report linter (`/pbg-report` lint) warns on the
> common empty-fields gaps. Aim for every section to have at least
> scaffolding content — even mocked or PLANNED entries are better than
> blanks.

---

## Top-level required fields

| Field | Type | Lint? | Purpose |
|---|---|---|---|
| `schema_version` | int | — | `3` (v3) or `4` (v4 narrative-spine). New studies should use `4`. |
| `name` | str (slug) | — | Kebab-case slug. Must match the directory name. |
| `title` | str | — | One-line human-readable title (rendered in the rail + study card). |

## Lifecycle status fields (multi-axis, Pass A canonical)

Use the SIX axes, not the legacy single `status:` field. The dashboard
preferentially renders multi-axis status; legacy `status:` falls back
when the axes aren't set.

```yaml
design_status:           planning | in_progress | approved
implementation_status:   not_started | prototype | complete
simulation_status:       not_started | ran | failed
evaluation_status:       not_started | evaluating | evaluated
gate_status:             pending | blocked | passed | failed
expert_review_status:    not_requested | requested | reviewed
```

Legacy `status: planned | running | complete | …` is still read as a
fallback (linter warns: `status_legacy_only`).

## Dependencies / DAG (Pass A canonical)

```yaml
pipeline_gate:
  prerequisites:
    - {study: <upstream-slug>, condition: tests-passed}
  enables:
    - <downstream-slug-1>
    - <downstream-slug-2>
  proceed_condition: |
    Concrete acceptance criteria for moving to the next phase…
  blocks_until_resolved: |
    What to do if proceed_condition fails (alternative paths)…
```

Legacy `parent_studies:` is still read as a fallback (linter warns:
`dag_edges_legacy_only`).

---

## Build tab — what to populate

The dashboard's study-detail "Build" tab renders from these fields. If
all are absent, the tab is BLANK.

### `conditions:` (v4 canonical — most important)

```yaml
conditions:
  baseline:
    composite: <pkg>.composites.<name>   # required
    params:
      key: value                         # optional
  variants:
    - name: <variant-slug>
      base_composite: <pkg>.composites.<name>  # or inherits baseline
      parameter_overrides: {key: value}
      description: |
        What this variant tests and why.
  model_settings:                        # human-set parameters
    - name: <slug>
      type: number | integer | string | boolean
      default: <value>
      current: <value>                   # user-editable in the UI
      range: [min, max]                  # for number types
      gate: required-before-run | informational
      description: <one line>
```

The dashboard renders three sub-sections per the above. The
`model_settings` items with `gate: required-before-run` block the run
button until a value is set. Linter check:
**`missing_conditions_block`** (warning).

### Legacy v3 fields (still read but linter-warns)

```yaml
baseline:                # list of mappings, v3 shape
  - name: <slug>
    composite: <pkg>.composites.<name>
    params: {...}
variants:                # v3 top-level list (alongside the above)
  - name: <slug>
    description: ...
    params: {...}
```

The linter (`missing_baseline`, `missing_variants`) accepts EITHER v3
OR v4 — but the Build tab only renders the v4 `conditions:` shape.
Carry both for back-compat OR convert to v4 entirely.

### Other Build-tab fields

- `model_change`: free-form description of what code/model change this
  study introduces (used in the per-study walkthrough).
- `implementation_requirements`: list of concrete deliverables the
  study needs from the engineering side.

---

## Simulations tab — what to populate

### `simulation_set:` (v4 canonical)

```yaml
simulation_set:
  - name: <run-slug>
    kind: single | sweep                # 'sweep' enables the multi-axis sweep UI
    status: planned | ready | running | completed | failed
    base_model: <pkg>.composites.<name>
    duration_steps: <int|string>        # or duration: <s> / duration_min: <m>
    seeds: [0, 1, 2, ...]               # optional
    metrics: [<readout-name>, ...]      # observables to collect
    pass_fail_tests: [<test-name>, ...] # which expected_behavior entries to apply
    details: |
      Brief one-paragraph why-this-run-matters.
  - name: <sweep-slug>                  # sweep form
    kind: sweep
    base_model: <pkg>.composites.<name>
    axes:
      - parameter: <param-path>
        values: [v1, v2, v3, ...]
      - parameter: <other-param>
        values: [a, b]
    seeds: [0, 1]
    metrics: [...]
    pass_fail_tests: [...]
    candidate_selection: |
      How candidates are picked from the sweep results.
```

Linter check: **`missing_simulation_set`** (warning).

### Legacy v3 `planned_runs:` (informational, NOT rendered by Build/Sims tabs)

```yaml
planned_runs:
  - name: <run-slug>
    status: planned | ran | completed
    n_steps: <int|string>
    details: <one line>
```

The linter accepts this for `missing_planned_runs`, but it doesn't
populate the Simulations tab. Convert each entry to a `simulation_set`
entry too.

---

## Other study-card sections

| Field | Lint check | What it drives |
|---|---|---|
| `expected_behavior:` (= tests) | (separate `_check_expected_behavior_dsl`) | Predicted-behavior table on the study card |
| `readouts:` (list of dicts) | `missing_readouts` | Readouts table on the study card |
| `visualizations:` (list of {name, address, description}) | `missing_visualizations` | Inline iframe viz cards |
| `bibliography.bib_keys` | (cross-reference check) | References footer + per-test citation |
| `report:` block | (none) | Rich panel chrome — Conclusion / Insight / Caveat / key_metrics chips |

### `readouts:` shape

```yaml
readouts:
  - name: <readout-slug>
    status: planned | implemented | gated | failed
    path: <on-disk-path-where-it-lands>   # e.g. ".pbg/runs/<id>/store.zarr"
    units: <units string>
    notes: <one-line description>
    blocked_by_requirements: [<req-id>]    # optional
```

### `visualizations:` shape

```yaml
visualizations:
  - name: <viz-slug>
    address: file:reports/figures/<study>/<file>.html
            | dashboard:study_charts
            | url:https://example.com/path
    description: <one-paragraph caption visible in the report>
```

The dashboard renders each entry as an iframe (file:) or chart (dashboard:).

---

## Lint checks summary (warning-level)

| Check | Field | Triggers when |
|---|---|---|
| `missing_baseline` | `baseline` or `conditions.baseline` | both absent |
| `missing_variants` | `variants` or `conditions.variants` | both absent / empty |
| `missing_conditions_block` | `conditions:` (v4) | absent AND no `model_change` / `implementation_requirements` |
| `missing_simulation_set` | `simulation_set:` | absent / empty |
| `missing_planned_runs` | `planned_runs:` and `runs:` | both absent |
| `missing_readouts` | `readouts:` | absent / empty |
| `missing_visualizations` | `visualizations:` | absent / empty |
| `status_legacy_only` | multi-axis status absent | only legacy `status:` set |
| `dag_edges_legacy_only` | `pipeline_gate:` absent | only legacy `parent_studies:` set |
| `narrative_spine_completeness` | v4 narrative sections | info-level nudge per missing section |

All warning-level checks are NON-BLOCKING — a study can still pass
`/pbg-report` lint with them. They surface the gap so the next round
of scaffolding closes it.

---

## Worked example — scaffolding a new study from scratch

Run from a workspace root:

```bash
/pbg-investigation new my-investigation
/pbg-study new my-study --composite v2ecoli.composites.baseline.baseline
```

That gives you a minimal `study.yaml` with just `name` / `title` /
`status: planned`. Then iteratively add:

1. **Multi-axis status + pipeline_gate** (replaces legacy fields)
2. **`conditions.baseline.composite`** (one line, fixes Build tab)
3. **`simulation_set`** with at least one entry per planned variant
4. **`readouts`** — list each observable you plan to measure
5. **`expected_behavior`** — DSL test entries (name + en + measure + expect)
6. **`visualizations`** — at minimum one `file:`-addressed PLANNED-mockup
   per study so the expert sees a concrete figure

Re-lint after each step (`/pbg-report --lint`) until 0 warnings remain.

---

## When to use v3 vs v4

| | v3 | v4 |
|---|---|---|
| Top-level `baseline` / `variants` | required | optional (back-compat) |
| `conditions.{baseline,variants,model_settings}` | n/a | required for Build tab |
| `simulation_set` | n/a | required for Simulations tab |
| Narrative spine (`study_card`, `readouts`, `conclusion_verdicts`, …) | partial | full |
| Lifecycle: `status:` enum | required | optional (replaced by multi-axis) |

**New studies should use v4 throughout.** v3 fields are retained as
back-compat for already-existing studies; the dashboard renders both
where a fallback is wired, but the modern tabs (Build, Simulations)
ONLY render the v4 fields.

# Study Run/Outcome Spine — Design

**Date:** 2026-06-09
**Status:** Draft (awaiting review)
**Scope:** First sub-project of a ~5-part program to move investigation/study "information propagation" out of agent-prose and into code.

---

## 1. Problem

Today, when a study runs simulations and tests, **no code writes the results back into the study.** Run data lands in the emitter store (parquet / xarray-zarr / sqlite) and pytest writes only an aggregate `tests.last_results`, but the study's verdict pills and per-test status read `runs[].outcomes[<test>].result` — a field **nothing populates**. So an agent hand-transcribes every run's numbers and PASS/FAIL into the study.

Concrete symptoms (from `v2e-invest/studies/dnaa-1-expression/study.yaml`):

- A literal workaround comment (lines 573–575, 816–818): *"the report reads the LAST run's `outcomes:` for the test pills, so the canonical run is placed LAST and carries the per-test results."* The agent hand-orders runs and hand-writes outcomes. A `canonical: true` flag already sits in the YAML (line 816) that nothing reads.
- Three disconnected "did it pass" sources: `runs_meta` (DB), `tests.last_results` (study aggregate), `runs[].outcomes` (per-test, never written). The DAG gate reads a *different* one (`tests.last_results` / `tests[].status`) than the verdict strip (`runs[].outcomes`) — so a study can read "unlocked" in the graph while showing "pending" in its own verdict.
- The per-run **Result** prose in each study (`gen 1: tau=77.0 … oriC {1,2,4}`, cycle-means, in-band checks) is arithmetic an agent does by hand from the run data.

The tests themselves are *already* a structured mini-DSL, not free prose:

```yaml
measure: {kind: range_check_per_generation, path: listeners.monomer_counts, window: full_lineage_from_gen_0}
pass_if: {op: in_range_every_generation, low: 300, high: 800}
```

so code can compute most PASS/FAIL calls directly from the run data.

## 2. Goal

Make **running a study's sims/tests automatically record the runs and compute the per-test outcomes**, writing one code-owned outcome surface that the verdict pills, DAG gate, acceptance criteria, and report all read. The human/agent's remaining job shrinks to the interpretive layer (finding statements, biology narrative, hypothesis framing) authored *on top of correct numbers*.

This is the **spine** the rest of the program builds on (coded gate/verdict rollup; expert-doc inflow; sim-set autofill; biology-forward results).

### Non-goals (explicitly out of scope for this spec)
- Rolling member findings/verdict up to the investigation, evaluating `acceptance_criteria` / `gate_evaluator.expr` (next sub-project, *enabled* by this one).
- Expert-document → study inflow, simulation-set auto-fill, biology-narrative generation (later sub-projects).
- Changing how simulations are launched or how trajectories are stored.

## 3. Approach

**Approach B — record + evaluate** (with **A — record + reflect** as the guaranteed-shippable first increment inside it):

- **A (ships first):** execution auto-records `runs[]` (metadata, emitter/store, params, seeds, timestamp, commit, `canonical` flag); the verdict pills / DAG gate / acceptance all read one source; canonical run chosen by flag, not array position.
- **B (layers on):** a coded evaluator runs the closed `measure`/`pass_if` DSL against the run's emitted data → computes `measured_value` + PASS/FAIL/PARTIAL automatically (+ `calibration_anchor.divergence_factor`). Tests outside the closed vocabulary fall back to the agent, clearly flagged.

Source-of-truth: trajectories stay in the emitter store; **evaluated outcomes are stamped back into `study.yaml` deterministically (regenerable, never hand-edited)** — portable/reviewable study, one upstream source.

## 4. Architecture

### 4.1 One outcome engine (`study_outcomes`)

A single module — `pbg_superpowers/study_outcomes.py`, alongside the existing `study_status` / `study_findings` / `study_verify` / `seed_from_followup` family — is the one place that knows how a run becomes outcomes. Pure function:

```
(study.yaml behavior_tests) + (a run's emitted data) ──▶ runs[].outcomes + per-run metrics stamp
       measure/pass_if            via the unified reader        PASS·FAIL·value + provenance
```

The dashboard already depends on `pbg-superpowers`, so the dashboard endpoints call the same engine — no reverse dependency, no third copy.

### 4.2 Emitter-aware reader (in `pbg-emitters`)

Runs are persisted by one of three emitters — **parquet / xarray-zarr / sqlite** — chosen by the workspace/investigation `default_emitter`. The reader's whole job is to abstract over them:

```
read(run) ──▶ uniform series/table interface   (engine never knows the backend)
```

This belongs in `pbg-emitters` because it owns the *write* side of all three (`parquet_emitter.py`, `sqlite_emitter.py`, `xarray_emitter/`) and already has read/view code (`xarray_emitter/view.py`). The dashboard's per-backend read logic (`vivarium-dashboard/lib/simulations_index.py::_resolve_emitter`, `:504`) **moves down** into `pbg-emitters`, de-duplicating it; the dashboard then imports it too.

### 4.3 Observables resolve against the `emit` config

Each emitter is configured with an `emit` declaration (`process-bigraph/emitter.py:48,104` — `config = {'emit': …}`). That declaration *is* the list of saved observables and their state-tree paths. The structured selector's `observable` id resolves through the run's emit config: engine reads emitter config → observable→path map → reader pulls that path from whichever backend. Portable across studies/composites/emitters.

Fallback for old runs with no recorded config: the reader enumerates available observables straight from the store (parquet columns / zarr variables / sqlite columns).

### 4.4 Decoupled from launch

Launchers don't change how they run sims. A separate **sync step** reads the store + the study's tests, evaluates, and stamps `study.yaml`. Triggered three ways, all calling the same engine:

1. **Auto after a run** — the dashboard `run-baseline`/`run-variant` endpoints and the CLI `run-script`/`canonical_runs` runner call `study_outcomes.sync(study)` on completion.
2. **On demand** — `pbg-study sync-runs <slug>` (CLI) and `/api/study-sync-runs` (dashboard).
3. **Idempotent** — re-running reproduces the stamp from the store (derived, not accumulated).

### 4.5 Single source of truth

After sync, the canonical run's `outcomes` is *the* outcome surface. `study_status`, the DAG gate, the verdict pills, and `acceptance_criteria` all read it; `tests.last_results` becomes a derived view of it. This removes the "unlocked-in-graph / pending-in-verdict" split.

## 5. The evaluator (closed DSL)

Keep the existing `measure:{…}` + `pass_if:{…}` shape; formalize a **small, closed, versioned vocabulary**.

- **`measure`** → extracts a value or series: `observable` (id), optional `aggregate` (e.g. `{sum_over: dnaA_forms}`), `window` (`every_generation`, `peak_of_each_cycle`, `gens: 4-7`, …). Output: scalar | per-generation series | per-cycle series.
- **`pass_if`** → predicate: `in_range`, `cv_below`, `within_tolerance_of`, `subset_of` (e.g. oriC ⊆ {1,2}), `every_generation(…)`. Output: PASS | FAIL | PARTIAL + `measured_value`.

(Exact operator list finalized in the implementation plan; the property that matters is *closed set*.)

### 5.1 Structured selectors (resolver discipline — chosen)

Prose qualifiers migrate into structured fields (`observable` id + explicit `aggregate`/index + `window` enum/struct) so measures are executable. A resolver maps known observables→columns (via the emit config, §4.3) and detects generation boundaries from division events. **Anything unresolvable is never guessed** — it routes to the agent bucket. Legacy prose `path:` still parses → agent bucket, so nothing breaks before migration.

### 5.2 Three evaluation buckets

Every outcome stamps `evaluated_by`:
- **code** — closed-vocab DSL, resolvable selector → engine computes it.
- **pytest** — behavior-test path (fast-follow; today only an aggregate exists).
- **agent** — free-form judgment; engine leaves a structured empty slot.

### 5.3 Provenance & trust

Every coded outcome stamps `{result, measured_value, evaluated_by, operator, inputs, run_id}` — reproducible and auditable. **Trust-reconciliation gate:** the first time the evaluator computes a test that was previously agent-judged, it surfaces a diff (*code says PASS: cycle-mean 362 ∈ [300,800]; prior prose said PASS*) for expert sign-off that the operator matches intent. Once signed off, it runs silently.

## 6. Data shape

Two code-owned blocks per study, regenerable, marked `# generated by study_outcomes — do not hand-edit`:

```yaml
runs:
- name: <run-id>
  kind: <run kind>
  status: completed
  emitter: {kind: parquet|xarray|sqlite, store: <path-or-db>, emit_config_ref: <ref>}
  seeds: [..]
  params: {perturbations: {...}, cache_provenance: {...}}
  timestamp: <iso>
  commit: <sha>
  canonical: true|false           # set by flag, never by array position
  metrics: {<per-gen / per-window numbers the report 'Result' block renders>}
  outcomes:
    <test-name>:
      result: PASS|FAIL|PARTIAL|SKIP
      measured_value: <scalar/series>
      evaluated_by: code|pytest|agent
      operator: <op id>            # for code/pytest
      detail: <short>
```

**Schema additions** (`study.schema.json`): `behavior_tests[].measure` gains `observable` / `aggregate` / `window` structured fields; `pass_if.op` constrained to the closed set. Legacy `path:` retained as accepted-but-agent-routed.

## 7. Triggers & integration points

| Path | Where | Change |
|---|---|---|
| Auto after run (UI) | `vivarium-dashboard` `run-baseline`/`run-variant` endpoints | call `study_outcomes.sync(study)` on completion |
| Auto after run (CLI) | `pbg-superpowers` `run-script` / `canonical_runs` runner | same call |
| On demand (CLI) | `pbg-study sync-runs <slug>` | new subcommand |
| On demand (API) | `/api/study-sync-runs` | new endpoint |
| Read | dashboard verdict pills, DAG gate, acceptance, report; `study_status` | read canonical `outcomes` |

## 8. Migration

A one-time, agent-assisted pass:
1. Convert existing studies' prose `measure.path` → structured selectors.
2. Back-fill `runs[].outcomes` + `metrics` from existing emitter stores via the reader.
3. Studies not auto-convertible stay in the agent bucket — no regression.

First corpus: the `dnaa-0` / `dnaa-1` studies (richest, known-correct outcomes — also the golden-test fixtures).

## 9. Edge cases

- **Partial/truncated run data** (the per-gen emit-truncation bug in the reference report): resolver detects the missing window and marks the test `needs_rerun` — **never PASSes on partial data**.
- **No `canonical` flag:** newest completed run + a lint nudge to set one.
- **Unresolvable observable/window:** agent bucket + reconciliation prompt; never a fabricated PASS.
- **Stale stamp** (latest run newer than stamp): flagged like the existing viz-freshness check.
- **Emitter config absent** (old runs): reader enumerates observables from the store directly.

## 10. Testing

- **Golden-study fixtures:** run the evaluator against `dnaa-0`/`dnaa-1` real stores; assert it reproduces the signed-off PASS/FAIL + `measured_value`s.
- **Resolver units:** observable→column (per backend), window→rows, generation-boundary detection.
- **Idempotency:** sync twice → byte-identical stamp.
- **Never-guess:** unresolvable measure → agent bucket, not a fabricated PASS.
- **Single-source:** gate, verdict, acceptance all read the same canonical `outcomes` in a fixture where they previously disagreed.

## 11. Risks & open questions

- **Reader extraction into `pbg-emitters`** is the biggest cross-repo move; if deferred, the fallback is a thin reader inside the engine, converging later (lower leverage, accepted only if the extraction proves too costly this pass).
- **Generation-boundary detection** depends on runs carrying division markers; confirm all three emitters expose enough to segment a lineage (or record gen boundaries at run time).
- **Operator vocabulary completeness:** the closed set must cover the common tests without becoming a general expression language. Start from the operators actually used across existing studies; extend deliberately.
- **pytest-capture (bucket 2)** is scoped as a fast-follow, not in the first increment, unless cheap.

## 12. Downstream (why the spine comes first)

Once `runs[].outcomes` is coded and single-sourced: gate/verdict/acceptance roll-up becomes a pure function over it; the report's run panels, test pills, gate decisions, and "Result" numbers render from it; and "bring the biology forward" becomes authoring narrative on top of correct numbers rather than transcribing them. The shared `emit`/observables vocabulary established here also feeds the later sim-set-autofill and `observables:` work.

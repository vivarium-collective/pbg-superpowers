---
name: viva-study
description: Use when managing a Study through its lifecycle (Design → Build → Simulate → Evaluate → Decide) in the workbench — creating or editing baseline composites, variants, interventions, runs, findings, and conclusions on a study.yaml.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: "<subcommand> [args] — full subcommand index in SKILL.md"
---

# /viva-study

The end-to-end interface for **Studies** in the vivarium-workbench, organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide; see [`docs/concepts/vivarium-workbench-model.md`](../../docs/concepts/vivarium-workbench-model.md#study-lifecycle)).

## Layout (investigation-centric, nested)

Studies live **nested under their investigation**:
`investigations/<inv>/studies/<slug>/study.yaml`, each carrying an `investigation: <inv>`
back-ref. The investigation's publication/report lives at `investigations/<inv>/reports/`
(per-investigation — there is **no global repo-wide report**).

- **Resolve a study dir** (nested- and flat-aware): studies live at `investigations/<inv>/studies/<slug>/` (nested) or legacy flat `studies/<slug>/`. The workbench endpoints resolve the slug server-side; when a subcommand needs a local file, check the nested path first, then the flat one.
- **Create a new study** under `$INVESTIGATIONS_DIR/<inv>/studies/<slug>/` (write the `investigation:` back-ref).
- Legacy flat `studies/<slug>/` still resolves (back-compat) until a repo is migrated with `viva-migrate-nested`.

This block governs the paths below: where older text says `studies/<slug>/` or `$STUDIES_DIR/<slug>/`, prefer the resolver / the nested path.


A Study is a self-contained research unit holding one-or-more baseline composites, variants (parameter perturbations), interventions (text-described conditions), runs, and visualizations. The **Build** phase between Design and Simulate doesn't have pbg-study subcommands directly — it's handled by `/viva-expert` (heavy mode → sibling repo) or `/viva-expert --lightweight` (in-workspace, single-tool or composite form), or by hand-edited code in `pbg_<workspace>/processes/`.

## See also — viva-expert → investigation → study → run → publish

This skill sits at step 3 of the showcase chain: [`/viva-expert`](../viva-expert/SKILL.md)
scaffolds the investigation + its member studies (`investigation-from-wrapper`);
studies are grouped by [`/viva-investigation`](../viva-investigation/SKILL.md)
(step 2, one level up); a study's individual composites can be smoke-tested
directly via [`/viva-run`](../viva-run/SKILL.md) (step 4, sibling to
`run-baseline`/`run-variant` below); and the finished workspace is published
read-only via [`/viva-workbench`](../viva-workbench/SKILL.md) (step 5).

<!-- House rules distilled from a cross-study expert-feedback friction review. General to any investigation. -->
## House rules (expert-feedback guardrails)

1. **BIAS TO EXECUTE.** Once a plan/design is approved, run the full loop before
   handing back: run the canonical simulation → record `runs[].outcomes` → run the
   study's behavior tests → report. Don't stop at a plan, an observer, or a stub,
   and never leave tests pending for the reviewer to request — testing is part of
   the run, not a follow-up.
2. **PROVIDED-MECHANISMS-ONLY (honesty).** Never introduce mechanisms, parameters,
   or outside literature that weren't explicitly provided in order to force a target
   result. If the target isn't met with the provided model, report it as an
   **HONEST OPEN QUESTION** — do not patch it into a pass. (The classic rejection is
   an un-provided literature value, or an extra cap/sink/term added solely to hit a
   number.) See the **Reference / mechanism discipline** section below for how to
   record an un-provided input as a `pending` proposal instead of silently using it.
3. **FRESHNESS on every re-run.** When a new canonical run lands, check each chart
   against `viva_superpowers.chart_store.classify_charts(study_dir)`:
   - If it's classified `superseded` → `git rm` the file in the same edit as the
     new run. Charts auto-discover from the dir, so an orphaned file reappears.
   - If a `visualizations[]` entry's presentation is one you want to keep →
     re-render it against the canonical run via `refresh-viz` (this re-points it
     at fresh data without deleting the view).
4. **SELF-SERVE the standard asks** — don't make the reviewer request them every
   study. Default to: steady-state framing where early transients distort a metric
   (use the steady-state window/average, not the warm-up); axis labels with units;
   and run-config provenance (record the exact parameter set used for each run).
5. **CALIBRATE WITH A SWEEP, not one value at a time.** To put a knob in a band,
   sweep a grid × multiseed in one pass and pick the recommended in-band point
   with provenance, instead of iterating single values.

**The letter is the spirit.** These rules cost effort exactly when you're under
pressure to skip them — a target that won't hit, a reviewer waiting, a run you'd
rather not repeat. Talking yourself past one is breaking it. Common excuses, and
the reality:

| Excuse | Reality |
|---|---|
| "The expert would obviously approve this classic reference." | If they didn't provide it, it's a `pending` proposal, not a fact (rule 2). Record it; don't cite it as evidence. |
| "The target is 28±3 and I got 24 — a modest recalibration is expected." | Recalibrating to hit a number IS forcing the result. Sweep for an in-band point with provenance (rule 5), or report the miss as an HONEST OPEN QUESTION. |
| "Adding a small sink/cap term is just numerical hygiene." | An un-provided term added to move a metric is a fabricated mechanism (rule 2). Propose it `pending`; don't bake it in. |
| "I'll keep the old chart too, just in case." | Stale charts auto-reappear and mislead reviewers (rule 3). Delete the file; re-render the view you value against the new run. |
| "Tests can run after I hand back — the result is the run." | Testing is part of the run (rule 1). A verdict without this session's test output is a claim, not a result. |

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`. Fail if not found.
2. Read `.pbg/server/server-info` for the dashboard URL. If absent, fail with: "Run `/viva-workbench start` first."

## Tests on a Study (v4 schema)

A study's **acceptance criteria live in the `behavior_tests:` list** in
`study.yaml` — the `(given, measure, expect)` grammar (see
[`docs/concepts/expected-behavior-grammar.md`](../../docs/concepts/expected-behavior-grammar.md)).
This is the load-bearing form: the evaluators, the report-card axes, the audit,
and the Tests tab all read it, and it's what studies actually use. **Author your
criteria here** via the `/viva-study` Design/Evaluate subcommands — start here,
not with the pytest directory below.

For **graded report-card tests** — axes with a signed `margin` (distance-to-pass),
`severity`, cited acceptance bands, and a cross-iteration diff (the agent-feedback
signal for iterative model building) — use [`/viva-tests`](../viva-tests/SKILL.md)
(`author` / `enrich` / `run`). It builds on `viva_superpowers.check()`/`TestBuilder`
and complements the `behavior_tests:` acceptance grammar above.

### Optional: a `tests/` pytest subdirectory (dashboard-only)

A study MAY *additionally* carry a `tests/` subdirectory of pytest files, for
**executable invariants that need real arrays** rather than a scalar compared
against a band (e.g. a per-feature round-trip over thousands of features). This
is an **optional, dashboard-only extra** — no study is required to have one, and
in practice most don't (the `tests:` mapping in `study.yaml` —
`auto_discover` / `data_source` / `pytest_args` / `last_results` — only
configures this runner; it is inert without a `tests/` dir):

- The dashboard runs them via `POST /api/study-tests-run {study}` and writes a
  summary to `study.yaml.tests.last_results`; the Tests tab shows per-test
  pass/fail with expandable tracebacks.
- The `run` fixture comes from `vivarium_workbench.testing`, so this path is
  available **only where the workbench is installed** (the dashboard side) — not
  from a consuming workspace's own venv. Reach for `tests/` only when a
  `behavior_tests` band genuinely can't express the invariant.

Tests use a `run` pytest fixture provided by `vivarium_workbench.testing`:

```python
# studies/<slug>/tests/conftest.py
from vivarium_workbench.testing import run  # noqa: F401

# studies/<slug>/tests/test_steady_state.py
def test_dnaA_count_in_range(run):
    assert 300 <= run.final("DnaA_count") <= 800
```

`Run` exposes: `.observable(name) → np.ndarray`, `.final(name)`, `.initial(name)`,
`.cv(name)`, `.params`, `.seed`, `.status`, `.n_steps`, `.variant`, `.composite`,
`.trajectory` (pandas DataFrame).

For studies that need to parametrize across all runs, set
`study.yaml.tests.data_source: all_runs` and use the `runs` fixture
(parametrized) instead.

### Band / steady-state criteria — default to the generation AVERAGE

When a test asserts a metric is "in band" over a multi-generation lineage, write
it as a **generation-average / steady-generation** check, NOT strict
per-generation. Early generations stabilize after a burned-in resume, and pools
that double-then-halve per cycle (DnaA, mass, counts) cross the band within a
cycle by design — both are expected, neither is a failure. So prefer:

```python
def test_dnaA_atp_fraction_in_band(run):
    # generation-average (drop the stabilizing first gen), not every tick
    per_gen = run.per_generation_mean("dnaA_ATP_over_total")
    assert 0.2 <= mean(per_gen) <= 0.5            # aggregate criterion
    # NOT: assert all(0.2 <= g <= 0.5 for g in per_gen)   # over-strict
```

Use the strict per-generation form ONLY when a reviewer explicitly requires it.
Picking the strict reading and recording a FAIL when the aggregate passes wastes
a review round (and often a confirmatory sweep). See
[handling-investigation-feedback.md#acceptance-criteria](../../docs/conventions/handling-investigation-feedback.md)
for the full rationale and the signals that the aggregate is intended.

## Cross-study dependencies (inputs.from — canonical)

A study declares its ordering (DAG) edges against other studies via the
**canonical** top-level `inputs:` list — each entry `{artifact: <slug>, from:
<slug>}`, and the DAG edge set is the `from:` slugs. This is the form the
v2ecoli workspace conformance test requires (it rejects the legacy
`parent_studies` / `pipeline_gate.prerequisites` fields).

```yaml
# studies/dnaa-02-atp-hydrolysis/study.yaml
inputs:
  - {artifact: dnaa-01-expression-dynamics, from: dnaa-01-expression-dynamics}
  - {artifact: dnaa-03-box-binding,         from: dnaa-03-box-binding}
```

**Legacy forms (back-compat, still accepted — a warning, never a hard error):**
`parent_studies:` (oldest) and `pipeline_gate.prerequisites:` (interim). Each
entry is either a bare slug or an object `{study, condition}` where `condition`
is one of `tests-passed` | `ran` | `complete`. New studies should use
`inputs.from`; the report linter warns any study still on a legacy field to
migrate. The discourse-graph `relation:` semantics below are still authored on
`parent_studies[]` for edge styling — that is a rendering concern separate from
the ordering DAG.

```yaml
# LEGACY (back-compat) — prefer inputs.from above
parent_studies:
  - dnaa-01-expression-dynamics                       # legacy: tests-passed
  - {study: dnaa-03-box-binding, condition: ran}      # object: parent must have ≥1 run
```

The dashboard's `GET /api/investigations` resolves these to per-study
`blocked` + `blocked_by` (parent + condition + missing-diagnostic), and
the Studies tab's `Dependencies` sort (default) topologically orders
the cards. Cards show `Depends on:` / `Blocks:` link chips and a
`🔒 blocked` pill with diagnostics in the tooltip when blocked.

A parent slug that doesn't resolve to a real study shows up as
`parent-not-found` in `blocked_by`, so dead references are visible.

## Investigation-graph fields: title · claim · confidence · relation

The dashboard renders the investigation page as an **Investigation graph** (a
discourse/knowledge graph) where each study is a node framed as **Question
(Asks) → Evidence (Finds) → Confidence**, with edges showing what a result
*leads to*. Four study-level fields drive that rendering. **All four are
optional** — the dashboard derives a fallback when absent — but authoring them
explicitly makes the graph read correctly instead of guessing from slugs and
status. They sit alongside the existing fields the graph already reads:
`question:` is the node's "Asks", `findings:` are the produced Evidence, and the
6-axis status feeds the derived confidence.

| Field | What it is | Dashboard shows | Derive-when-absent | Authored in |
|---|---|---|---|---|
| `title:` | human display name (the slug stays the technical id) | graph node label, study heading, nav | slug with the `<inv>-NN-` ordering prefix stripped + humanized | **Design** |
| `parent_studies[].relation:` | edge semantics on a dependency | solid edge (`leads-to`) or dashed edge (`regulatory` / `refutes` / `refines`); `supports` reinforces | `leads-to` | **Design** |
| `claim:` | one-line headline of the knowledge the study produced (what we now believe) | the node's "Finds" line | top `findings[].summary` | **Evaluate / Decide** |
| `confidence:` | the study's acceptance/confidence state | node badge | `viva_superpowers.study_verdict.derive_confidence(spec)` — the SAME value the left-rail dot reads, so the rail and the graph never disagree: the rolled-up/authored verdict wins (`report.verdict`/`gate_status`: passing→`Accepted`, failed→`Refuted`, needs_calibration→`Investigating`), else the lifecycle `status` (completed/complete/ran/evaluated→`Accepted`, running→`Investigating`, else `Planned`) | **Decide** (when the derived value is wrong) |

**Enums.**

- `confidence:` ∈ `Accepted | Investigating | Planned | Refuted`.
- `parent_studies[].relation:` ∈ `leads-to` (default) `| regulatory | supports | refutes | refines`. Renders solid for `leads-to`, dashed for `regulatory` / `refutes` / `refines`. Author the relation when declaring a dependency to express the discourse relationship, not just ordering. `refines` marks the finer-grained realization of the same claim as its coarser parent — pair it with a `refinement.must_preserve` + `satisfaction` block on the finer study (see [pbg-investigation § Multi-realization claims](../viva-investigation/SKILL.md)).

```yaml
# studies/<slug>/study.yaml
title: "DnaA-ATP hydrolysis"        # Design — keep it short; it appears in narrow graph cards
claim: |                            # Evaluate/Decide — what we now believe
  Intrinsic DnaA-ATP hydrolysis alone holds the ATP fraction near 30% at steady growth.
confidence: Accepted                # Decide — only when the status-derived value is wrong
parent_studies:
  - {study: dnaa-01-expression-dynamics, condition: tests-passed, relation: leads-to}
  - {study: dnaa-03-box-binding,         condition: ran,          relation: regulatory}
```

**Which subcommand sets each field.** `title:` and `parent_studies` (with
`relation:`) are naturally authored at **Design** time — `/viva-study new`
scaffolds the study, then add the `title:` line and wire `parent_studies` with
relations as you declare dependencies (these are YAML-direct; no dedicated POST
endpoint). `claim:` and `confidence:` belong to **Evaluate/Decide** — refresh
`claim:` once `findings:` exist (after `/viva-study findings`), and set
`confidence:` explicitly at Decide (alongside `/viva-study set-verdicts`) only
when the value derived from the 6-axis status is wrong.

## Grouping studies into Investigations

Studies that share a research arc can be grouped into an **Investigation** (a named collection with its own question/hypothesis + acceptance criteria). Studies don't declare investigation membership themselves; the investigation lists them in its `studies:` field. Use `/viva-investigation` for investigation CRUD and the `scaffold-from-plan` marquee command that auto-generates an investigation + all constituent studies from a plan PDF.

## Reference / mechanism discipline: NEVER silently add what the expert did not provide

When you cite a paper (`--cite`, `--source`, `cites:`, `literature_anchors[].source`) or lean on a mechanism, that reference/mechanism must be one the **expert actually provided or explicitly approved**. If, while building or evaluating a study, you reach for a paper, parameter, or mechanism the expert did **not** give you, do **not** quietly fold it into `cites:` / `literature_anchors` / the prose as if it were sanctioned. Record it on the parent **investigation** under `proposed_inputs:` with `status: pending`, a `provenance` (which commit / why it surfaced), and a `rationale` (what you used it for), and let the expert Accept or Decline it in the report. On Accept, a `kind: reference` item is promoted into the investigation's `inputs.references` and becomes a real provided reference (then it is fair to cite); a `kind: mechanism` item is marked accepted for a human to integrate. On Decline it is left out. See the `proposed_inputs:` schema in **pbg-investigation**. This guardrail keeps outside claims from entering the record as expert-sanctioned.

A cited/sanctioned parameter itself still needs its provenance labelled: `cites` (real literature value), `provenance: theory` with a "not fit" note (a deliberate, recorded modeling choice), or `proposed_inputs` (pending). Never let a `provenance: theory` value read as fit or data-anchored. See `/viva-cite-bands` § Step 3.

## Rigor pass (Evaluate → Decide): fill the required information so the scorecard goes green

Every study should carry the information a skeptical reviewer asks for. The
dashboard computes an **evidence & rigor scorecard**
that reports `ok`/`warn`/`gap` per dimension from declared fields, and the report
surfaces it — a missing field is a `gap`. Before a study is "done", address each
dimension (or say why not). Full guide + field shapes:
[`docs/conventions/rigor-checklist.md`](../../docs/conventions/rigor-checklist.md).

> **Insist on evidence, follow-ups, and decisions — don't finish a study silently.**
> These three are the easiest to skip and the first a reviewer misses, so when a
> study reaches **Evaluate/Decide you MUST actively prompt the expert for and fill
> them** — treat a study with any of them empty as **NOT done**, and ask before you
> set `confidence: Accepted`:
> - **Evidence** — every finding needs `evidence.observed` (the concrete measured
>   result, e.g. "recruitment index 0.77 vs 0.00 across 5 seeds, d=6.38"), not just a
>   claim. An empty `evidence` renders a **blank Evidence section** in the report.
> - **Follow-ups** — at least one `discovery_implications.followup_study_proposals`
>   (each with a real `motivation`), added via `/viva-study propose-followup`. A study
>   that answers a question always opens the next one — capture it, or the Follow-ups
>   section is blank.
> - **Decisions** — any choice the result forces: an open design decision
>   (`design_pivot_required` via `/viva-study add-pivot`) or a recorded conclusion.
>   If the result changes what to do next, that is a decision — record it, don't leave
>   it implicit.
>
> Don't wait to be asked for these at the end; surface them **as the study is being
> worked on** (a finding lands → prompt for its evidence and the follow-up it opens).

> **Real composites + emitters (both linted).** Every study must reference a
> **REAL registered composite** — `baseline[].composite` has to resolve in the
> workspace registry (run `/viva-catalog` to see what's installed; a typo or a
> not-yet-built composite shows up as an "error composite…" node and is flagged
> by `report_linter.unresolved_composite_refs`). And every study's runs must
> **persist via an emitter** (sqlite / parquet / xarray, or a run-db reference) —
> a study with runs but no emitter earns a `run_persistence` rigor `gap` and a
> `runs_without_emitter` lint warning.

In short, ensure the study declares:
- **a model** — `baseline:` with the composite(s) + params it runs (every study runs ≥1 composite, and the composite must be REAL/registered);
- **replication** — `robustness:` (≥3 seeds for stochastic; a `parameter_sweep: true` for deterministic);
- **controls & calibration** — `controls:` with a NEGATIVE control (a system that should fail — build it with the **Intervention process** to clamp/knockout/scale a store) AND a positive/borderline case;
- **alternative_hypotheses** — competing explanations + how the evidence (often the control) excludes them;
- **tiered findings** — each finding `tier: observation|mechanism|interpretation`, with `mechanism_origin: engineered|emergent` on interpretation claims;
- **falsifiability** — a `falsifiability:` note (what result would overturn the claim);
- **limitations** — what this does NOT show;
- **discovery_implications** — resolved/remaining uncertainties + `followup_study_proposals` (each with a real `motivation`, not just a title).

At the investigation level, ensure `competing_frameworks:` is set and at least
one member study is `kind: adversarial` (a system that should NOT qualify; the
metric passes by rejecting it). See `pbg-autopoiesis` for the reference shape
(every study 8/8, investigation 5/5).

### Render completeness — no blank tabs or sections

Rigor is about *what a reviewer asks*; this is about *what the dashboard draws*.
A study can be scientifically complete and still render with empty tabs because a
field the UI reads is absent. When building a study, fill these so nothing shows
blank — prompt the expert for each rather than shipping an empty section:

- **`conditions:`** — the study-detail **Build tab renders from
  `conditions.{baseline,variants,model_settings}`**, NOT from the top-level
  `baseline:`/`variants:`. A study with a populated `baseline:` but no
  `conditions:` block shows a **BLANK Build tab** (`report_linter` flags
  `missing_conditions_block`). Mirror the baseline into `conditions.baseline`
  (a mapping with a `composite:` — note the strict v4 validator requires
  `composite`, so a `step:`/`process:`-only baseline needs its dotted path there
  too, or the block is rejected) and add `conditions.model_settings: []`.
  **`model_settings` is read only as `conditions.model_settings`, and only on
  a v4 study** (`schema_version: 4`, what `/viva-study new` scaffolds) — a
  top-level `model_settings:` on a v3 study is authored-but-inert, not
  surfaced by the Build tab. Author calibrated params under v4
  `conditions.model_settings`, or migrate the study to v4 first.
- **`readouts:`** — the observables the run reports; without them the readouts
  section is empty. Validate every entry against the real composite output with
  `check-observables <slug>` (never fabricate an observable).
- **`visualizations:` / `embed_visualizations:`** — at least one figure or an
  embedded viewer, or the report has nothing to look at. Add via `/viva-viz`.
- **v4 narrative spine** — the 15 narrative sections (`behavior_tests`,
  `runtime`, `assumptions`, `enforced_params`, `literature_anchors`,
  `implementation_requirements`, …); `report_linter` warns
  `narrative_spine_completeness` with the exact missing set. Draft from plan +
  expert docs with `fill-overview <slug> --include-narrative`.

## Sub-commands

Organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide).
Every subcommand below has its full spec — arguments, endpoint/body shapes,
step-by-step behavior, notes — in **[reference.md](reference.md)**. This is a
compact index only; nothing here is the authoritative spec.

### Design

| Subcommand | Purpose |
|---|---|
| `new <composite-id>` | Create a new Study seeded with one baseline composite (writes v4-shape `study.yaml`). |
| `fill-overview <slug> [--from-plan <path>] [--from-expert <path>...] [--fields <list>] [--include-narrative] [--dry-run]` | Draft `question`/`hypothesis`/`objective`/`description` (+ optional v4 narrative fields) from plan/expert docs. |
| `set-objective <study-name> '<text>'` | Replace the Study's objective. |
| `baseline-add <study-name> --name <n> --composite <id> [--params '<json>']` | Append a composite to the Study's baseline list. |
| `baseline-remove <study-name> --name <n>` | Remove a baseline composite (blocked if variants depend on it). |
| `variant-add <study-name> --name <n> --base-composite <baseline-name> [--params '<json>']` | Add a variant (parameter perturbation) of a baseline. |
| `variant-set-params <study-name> --variant <n> --params '<json>'` | Replace a variant's parameter overrides. |
| `variant-delete <study-name> --variant <n>` | Remove a variant. |
| `intervention-add <study-name> --name <n> [--description '<text>']` | Add a text-described experimental condition. |
| `intervention-update <study-name> --name <n> --description '<text>'` | Update an intervention's description. |
| `intervention-delete <study-name> --name <n>` | Remove an intervention. |
| `add-literature-anchor <slug> --expectation '<t>' --model-observable '<t>' [--source '<t>'] [--status '<t>'] [--cite <bib-key>...] [--dry-run]` | Append a literature-expectation ↔ model-observable pair to `literature_anchors[]`. |
| `add-pivot <slug> --id <id> --question '<t>' [--alternatives 'A;B;C'] [--status <s>] [--requested-response '<t>'] [--notes '<t>'] [--dry-run]` | Append an open design-decision point to `design_pivot_required[]`. |
| `add-requirement <slug> --id <id> --title '<t>' [--kind <k>] [--effort XS\|S\|M\|L\|XL] [--status <s>] [--description '<t>'] [--step '<t>'...] [--unblocks 'a,b,c'] [--defer-until '<t>'] [--dry-run]` | Append a Build-phase TODO to `implementation_requirements[]`. |

### Design→Build gate

| Subcommand | Purpose |
|---|---|
| `verify <slug> [--strict] [--json] [--quiet]` | Spec-verify cross-references (behavior_tests, variants, parent_studies, cites, findings, followups) before a run. |
| `preview-viz <slug> [--name <viz-name>]` | Re-render declared `visualizations[]` against existing data to catch render errors early. |
| `check-observables <slug>` | Never-fabricate-observable guard: validate every `readouts[]` entry against the baseline composite's actual emittable structure. |
| `migrate-readouts <slug>` | Canonicalize legacy readouts (safe auto-rewrite) and drive un-parseable ones to guided re-authoring. |

<HARD-GATE>
Do NOT run-baseline / run-variant / run-script until `verify <slug>` AND
`check-observables <slug>` pass for this study. A run against an unverified spec or
a phantom readout burns the simulation and poisons `runs[].outcomes` with a result
you will have to throw away.
</HARD-GATE>

_"It's a 5-step smoke run, verify is overkill" — a phantom observable fails just as
fast at 5 steps as at 5000, and now the run is worthless. Verify first._

### Simulate

| Subcommand | Purpose |
|---|---|
| `run-baseline <study-name> [--composite <name>] [--steps N] [--no-refresh-viz]` | Run a baseline composite; auto-refreshes viz on success. |
| `run-variant <study-name> --variant <n> [--steps N] [--no-refresh-viz]` | Run a variant (base composite + parameter_overrides); auto-refreshes viz. |
| `run-script <study-name> [--entry <name>] [--list] [--no-refresh-viz]` | Run a study's bespoke runner script from `canonical_runs[]` (multi-gen / calibration harnesses that don't fit the composite executor). |
| `refresh-viz <study-name> [--no-auto]` | Re-render `visualizations[]` against the latest run and stamp freshness sidecars. |
| `clean <study-name> [--dry-run] [--include-out-paths]` | Wipe conventional simulator output (`runs.db`, `parquet-runs/`) for a from-scratch rerun; never touches git-tracked files. |

### Evaluate

No `/viva-study` subcommands run directly in this phase — evaluation is driven
by `POST /api/study-tests-run` (the Tests tab; results land in
`study.yaml.tests.last_results`) and by `/viva-viz` (add/render visualizations).

### Decide

<HARD-GATE>
No verdict, conclusion, or finding without fresh evidence from THIS session.
`set-verdicts`, `set-conclusion`, and `findings` write claims — and a claim you
cannot point to a command's output for is fabrication, not a conclusion. Before
writing each: identify what proves it, run it (or read the recorded artifact), and
read the output.
</HARD-GATE>

| Claim you're about to write | Requires (this session) | NOT sufficient |
|---|---|---|
| a run is `ran` / `completed` | `runs[].outcomes` recorded **and** artifacts on disk **and** committed | the run launched; the log "looked fine" |
| "band held" / a metric passed | reading `computed_outcomes[T].measured_value` against the band | eyeballing a chart |
| a track `verdict` = passed | every gating `behavior_test` green under the canonical run | one seed; one calibration point; `tests.last_results` from a prior session |
| "reproducible" | a re-run in the canonical env matches the fingerprint | the code is committed |

**Close out the lifecycle — advance `status` + `phase` when Decide is real.**
A study whose runs completed, whose `report.verdict` (or `pipeline_gate.gate_evaluator.result`) is written, and whose Decide content exists (`discovery_implications.followup_study_proposals`) is **done** — but if you leave it at `status: running` / `phase: Evaluate`, the three status surfaces disagree: the left-rail dot and the graph node read the verdict (green/Accepted) while the phase badge reads the stale phase (pink "Evaluate"). That is the single most common "why are my markers inconsistent?" trap. On genuine close-out set both, so all three surfaces agree by construction:

```yaml
status: complete   # badge-complete renders green; derive_confidence → Accepted.
                   #   Use `complete`, NOT `evaluated` — there is no badge-evaluated style.
phase:  Decide     # phase-decide renders green (phase-evaluate is pink).
```

Gate this on real evidence, never on wishful completion: advance ONLY when a `report.verdict` exists, the gate result ∈ {`passed`, `needs_calibration`}, and at least one `runs[]` entry is `completed`. A study missing its `report.verdict` falls back to the lifecycle `status` for its marker — so an otherwise-finished study with an empty `report` shows **Investigating** until you write the verdict. Write the verdict from the evidence the findings already record; don't advance a study that hasn't actually concluded.

If the evidence isn't there, the honest verdict is `blocked` or an OPEN QUESTION —
not `passed`. This is the discipline `/viva-harden-investigation` enforces
retroactively; applying it here means you rarely need it.

| Subcommand | Purpose |
|---|---|
| `set-conclusion <study-name> '<markdown>'` | Replace the Study's markdown conclusion (`## Claims` / `## Evidence` / `## Limitations` / `## Next steps`). |
| `set-verdicts <slug> [--regression ...] [--basis-regression '<t>'] [--biological ...] [--basis-biological '<t>'] [--explanatory ...] [--basis-explanatory '<t>'] [--dry-run]` | Write the v4 three-track `conclusion_verdicts` (regression_compatibility / biological_validation / explanatory_gain). |
| `findings <study-slug> [--auto] [--dry-run]` | Walk `behavior_tests[]` outcomes and propose structured `findings[]` entries not yet covered. |
| `propose-followup <parent-slug> --id <id> --title '<t>' --motivation '<m>' [--mechanism '<hyp>'] [--seed-from-file <path>] [--dry-run]` | Append a "we should also study X" entry to `followup_proposals[]`. |
| `seed-from-followup <parent-slug> <proposal-id> [--new-slug <slug>] [--from-finding <finding-id>] [--dry-run]` | Lift a followup proposal (or a finding, Pass 10B) into a new sibling study, linked back via `pipeline_gate.prerequisites`. |
| `feedback-respond <slug> [--apply] [--dry-run]` | Map open expert-feedback items to tracked actions (`next_action` / `finding` / `design-edit` / `study-seed`) and optionally apply them. |

**The terminal state of a study is `/viva-report` (no flags).** `set-verdicts` / `set-conclusion` are not the end — a verdict nobody has audited against the charts is not reviewer-ready.

### Utility

| Subcommand | Purpose |
|---|---|
| `open <study-name>` | Open the Study's detail page in the default browser. |

## Detailed reference

Full per-subcommand specs, flags, endpoint/body shapes, step-by-step behavior,
notes, the implementation outline, and worked examples are in
**[reference.md](reference.md)** in this skill directory.

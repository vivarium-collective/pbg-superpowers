# vivarium-workbench Data Model

The canonical concepts pbg-superpowers reads, writes, and orchestrates in a vivarium-workbench workspace. This document is the source of truth for vocabulary, on-disk shape, and the API surface that maps each concept to skill commands.

> **Companion repo:** [vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench). pbg-superpowers requires its server to be running for any skill that mutates dashboard state.

## At a glance

```
Workspace
  ├── Composites (in pbg_<pkg>/composites/, discovered by the catalog)
  ├── Studies (in studies/<name>/study.yaml — v4 with 14-section narrative spine)
  │     ├── Executive      (runtime, report, study_card)
  │     ├── Framing        (question, assumptions, conditions{baseline, variants,
  │     │                   model_settings, expert_inputs}, enforced_params)
  │     ├── Validation     (behavior_tests, readouts, biological_summary,
  │     │                   literature_anchors)
  │     ├── Implementation (model_change, implementation_requirements,
  │     │                   design_pivot_required, conclusion_verdicts)
  │     ├── Runs           (in runs.db — per-study SQLite; runs[] in YAML is deprecated)
  │     └── Visualizations (list of named viz configs)
  ├── Investigations (in investigations/<slug>/investigation.yaml — v2 with 9-section narrative spine)
  │     ├── executive, scientific_argument, biological_story, lead
  │     ├── at_a_glance, how_to_read, glossary, guidelines
  │     └── Studies[]      (list of study slugs; DAG from each study's inputs[].from — pipeline_gate.prerequisites is legacy)
  └── Visualization classes / registry (workspace-wide)
```

## The concepts

### Workspace

A directory containing `workspace.yaml`, a `pbg_<package>/` Python package, and the dashboard's runtime state under `.pbg/server/`.

- **On disk:** `<workspace>/workspace.yaml` + `pbg_<pkg>/`.
- **In the dashboard:** the root container; everything else lives inside it.
- **Created by:** `/pbg-init`.
- **`runtime:` block (optional).** Workspace-wide settings consumed by skills and runners:
  - `default_emitter: parquet | sqlite` — picked up by bespoke runners via `--emitter` default (see [`runner_scripts.md`](../conventions/runner_scripts.md)).
  - `subprocess_timeout_s: <int>` — overrides the dashboard's default per-tick subprocess timeout (used by long cell-cycle sims).
  - `shared_artifacts: [<path>, ...]` — workspace-root-relative paths expensive to rebuild (caches, precomputed indexes). `/pbg-investigation open <slug>` detects when these are absent in a new worktree but populated in a sibling, and (with `--share-artifacts`) symlinks them across. Default if absent: `["out/cache"]` (v2ecoli ParCa-cache convention).

### Study

A self-contained research unit: question + baseline composite(s) + variants + interventions + runs + visualizations + conclusion.

- **On disk:** `<workspace>/studies/<name>/study.yaml`. The schema accepts both `schema_version: 3` (legacy minimal) and `4` (current — adds the v4 narrative spine; see [v4 narrative spine](#v4-narrative-spine) below). Legacy v2 specs live at `<workspace>/investigations/<name>/spec.yaml` and are migrated to v3 in-memory on read.
- **Identity:** the directory name (a slug like `dnaa-02-atp-hydrolysis`). Use kebab-case lowercase slugs; v2-era random-hash names (`study-monod_kinetics-096184`) are legacy.
- **v3 shape (minimal):** `{schema_version: 3, name, objective, status, baseline: [...], variants: [...], interventions: [...], visualizations: [...], conclusion}`.
- **v4 shape (current):** v3 + the 14-section narrative spine: `runtime, report, study_card, question, assumptions, conditions, enforced_params, behavior_tests, readouts, biological_summary, literature_anchors, model_change, implementation_requirements, design_pivot_required, conclusion_verdicts`. All v4 fields optional. New scaffolds emit v4 (see [v4 narrative spine](#v4-narrative-spine)).
- **Created by:** `/pbg-study new <study-name> <composite-id>`. **Managed by:** `/pbg-study`. **Listed by:** `/pbg-catalog list`.

> "Study" is the canonical per-experiment term. "Investigation" now refers specifically to the higher-level collection container (`investigations/<slug>/investigation.yaml`). The v2 legacy use of "investigation" as a synonym for "study" is retired in the UI; backend aliases (`investigation:` body key, `/api/investigation-*`) remain for backwards compatibility but should not be used in new code.

### Study lifecycle (Design → Build → Simulate → Evaluate → Decide)

Studies move through five phases. Each phase has a distinct deliverable, distinct tools, and distinct evaluation criteria. The dashboard's `status` field captures the runtime sub-state within a phase (`planned`, `running`, `ran`, `complete`, `failed`, `invalid`); the phase itself is a higher-level coordinate that a Study declares via the top-level `phase:` field. The enum is **capitalized**: `Design | Build | Simulate | Evaluate | Decide` (the dashboard's `study-detail.html` reads `study.phase` directly).

| Phase | Produces | Skills / tools |
|---|---|---|
| **Design** | The spec: purpose, pipeline_gate, simulation_set, model_change, key_assumptions, readouts, behavior_tests, conclusion_logic, limitations, implementation_requirements, bibliography | `/pbg-study new`, `/pbg-study fill-overview`, `/pbg-study set-objective`, baseline/variant/intervention `*-add` subcommands, `/pbg-investigation new`, `/pbg-investigation scaffold-from-plan` |
| **Build** | The executable code: Process classes, listeners, composites that make the spec runnable against the workspace's simulator | `/pbg-expert` (sibling repo) or `/pbg-expert --lightweight` (in-workspace, single-tool or composite form), plus manual code in `pbg_<workspace>/processes/`. Gap-listed listeners + sim_data calibration also happen here. |
| **Simulate** | The runs: `runs.db` populated with trajectories | `/pbg-study run-baseline`, `/pbg-study run-variant`, `/pbg-study run-script` (bespoke runners declared in `canonical_runs:`) |
| **Evaluate** | The verdict: behavioral test results, rendered visualizations, observations against `behavior_tests` | `POST /api/study-tests-run` (Tests tab), `/pbg-viz` (Visualizations tab) |
| **Decide** | The conclusion: what we learned + next steps | `/pbg-study set-conclusion` |

The phases are sequential at a coarse level but **iterative in practice**: Evaluate often surfaces a Build issue → return to Build → Simulate again → re-Evaluate. The `phase:` field reflects the study's *current* phase, not its history.

Investigations aggregate over their constituent studies: an Investigation card surfaces the slowest-phase member (e.g., one study still in Design blocks the Investigation from leaving Design overall).

### Reviewer-facing status clarity

A recurring reviewer complaint is "I can't tell which studies ran, whether the tests ran, or whether the study passed." The fix is **derive-on-read + single-sourced**, not hand-set fields:

- **`viva_superpowers.study_status.study_clarity_summary(spec, runs)`** is the single source of truth. It returns one normalized object — `{ran, tests, verdict, ambiguities}` — that every renderer reads, so the run/test/verdict markers are computed **once** and shown consistently.
- **The test markers mirror the renderer exactly.** A study's per-test pill is derived from the **latest run's `outcomes[test_name].result`** (PASS/FAIL/SKIP), **not** from the test's own `status:` field. A test with `status: passed` but no recorded run-outcome renders **⏳ pending**. So to make a passing test *show* as passing, record `runs[].outcomes: {<test_name>: {result: PASS}}` on the latest run — see [handling investigation feedback](../conventions/handling-investigation-feedback.md).
- **`simulation_status` / `evaluation_status` are derived from `runs`**, never trusted from the stored field; a study that declares `status: completed` but records no `runs:` derives `not_run` and renders as "pending" despite the headline.
- **The downloadable report** (`walkthrough.js` `_buildInvestigationReportHtml`) renders a per-study **"Ran · Tests · Verdict" strip** from `study_clarity_summary` (server-injected as `spec.clarity_summary`, with an equivalent client-side fallback).
- **The report-linter guards this**: `status_claims_done_no_runs_recorded` (declares done but no run provenance) and `reviewer_clarity_ambiguity` (ran-but-every-test-pending, gate↔test divergence) both run in `pbg-report` Pass B, single-sourced from the same summary.

### 8-section canonical Study structure

A v3 `study.yaml` is organized into 8 user-facing sections plus two cross-cutting fields. Each section maps to a top-level YAML field. The shape below mirrors `studies/dnaa-01-expression-dynamics/study.yaml` in a v2ecoli workspace — read that file for live, expanded values.

| Section            | YAML field(s)                                            |
|--------------------|----------------------------------------------------------|
| 1. Purpose         | `purpose:` (`question` / `mechanism` / `expected_outcome`) |
| 2. Pipeline Gate   | `pipeline_gate:` (`enables` / `proceed_condition`). **DAG edges are canonically a top-level `inputs:` list of `{artifact: <slug>, from: <slug>}` — the edge set is the `from:` slugs.** `pipeline_gate.prerequisites` and `parent_studies` are legacy back-compat forms (v2ecoli workspace conformance requires `inputs.from` and rejects both legacy fields). |
| 3. Simulations     | `simulation_set:` (replaces v3 `variants:` + `interventions:`) |
| 4. Build           | `model_change:` + `implementation_requirements:`         |
| 5. Readouts        | `readouts:` (replaces v3 `observables:`; each carries `status` + `blocked_by_requirements`) |
| 6. Tests           | `behavior_tests:` (replaces v3 `expected_behavior:`; `tests:` is dashboard-v4 reserved so the field is renamed) |
| 7. Limitations     | `limitations:`                                           |
| 8. References      | `bibliography:` (`references:` is dashboard-v4 reserved so the field is renamed) |

Cross-cutting fields that sit outside the 8 sections:
- `key_assumptions:` — short biological context that pairs with section 4 (Build).
- `conclusion_logic:` — `if_primary_tests_pass:` / `if_primary_tests_fail:` mapping that pairs with section 6 (Tests).

Top-level lifecycle field:
- `phase: Design | Build | Simulate | Evaluate | Decide` — capitalized enum (see [Study lifecycle](#study-lifecycle-design--build--simulate--evaluate--decide) above).

Back-compat shims kept at the top level so v3-era dashboards still render:
- `baseline:` — mirrors one entry of `simulation_set:`; the v4 renderer should consume `simulation_set:` directly.
- `parent_studies:` and `pipeline_gate.prerequisites:` — both **legacy** DAG-edge forms, superseded by the canonical top-level `inputs:` list (`{artifact: <slug>, from: <slug>}`, edges = the `from:` slugs). Kept as back-compat for older dashboards; new studies should declare edges via `inputs.from` only (v2ecoli conformance rejects the legacy fields).

Minimal example (truncate values to placeholders; the schema accepts the loose shapes below — see [`study.schema.json`](https://github.com/vivarium-collective/pbg-template/blob/main/template/.pbg/schemas/study.schema.json)):

```yaml
schema_version: 3
name: <slug>
created: '<YYYY-MM-DD>'
status: planned
phase: Design        # Design | Build | Simulate | Evaluate | Decide

# v3 back-compat shim — mirrors simulation_set[0]
baseline:
  - name: <name>
    composite: <pkg.composites.x>
    params: {}

# 1. PURPOSE
purpose:
  question: |
    <one-paragraph research question>
  mechanism: |
    <which existing/new processes carry the answer>
  expected_outcome: |
    <quantitative or qualitative prediction>

# CANONICAL DAG EDGES — top-level inputs list; edge set = the `from:` slugs
inputs:
  - {artifact: <parent-slug>, from: <parent-slug>}   # this study depends on <parent-slug>

# 2. PIPELINE GATE  (DAG edges live in `inputs.from` above, NOT here)
pipeline_gate:
  enables: []                # list of child study slugs
  proceed_condition: |
    <when downstream studies may start>
  # prerequisites: []        # LEGACY back-compat; declare edges via inputs.from instead

# 3. SIMULATION SET
simulation_set:
  - name: <run-name>
    base_model: <pkg.composites.x>
    perturbation: null       # or {param_name: value}
    condition: <env-id>
    duration_min: 60
    seeds: [0, 1, 2]
    readouts: [<readout-name>, ...]
    applies_tests: [<test-name>, ...]
    status: ready            # ready | gated
    blocked_by_requirements: []   # only if status == gated

# 4. MODEL CHANGE (Build section)
model_change:
  base_model: <pkg.composites.x>
  new_processes: []
  new_state_variables: []
  new_parameters: []
  modified_processes: []
  new_listeners: []
  notes: |
    <one-paragraph "what code changes and what doesn't">

# Pairs with Build — short biological context
key_assumptions:
  - "<assumption 1>"
  - "<assumption 2>"

# 5. READOUTS
readouts:
  - name: <readout-name>
    description: |
      <what is collected and from where>
    store_path: <agents.0.listeners.x.y>
    units: <molecules/cell | uM | ratio | ...>
    status: available        # available | derived-needed | aspirational
    blocked_by_requirements: []     # populated when status != available

# 6. BEHAVIOR TESTS
behavior_tests:
  - name: <test-name>
    classification: primary  # primary | supporting | diagnostic | regression
    description: |
      <one-paragraph what this test asserts>
    measure: {kind: <primitive>, ...}
    pass_if: {op: <op>, ...}
    units: <unit>
    requires_simulation: <simulation-set-name>
    cites: [<bib-key>, ...]

# Pairs with Tests — explicit if/then
conclusion_logic:
  if_primary_tests_pass:
    implementation_status: "<one-sentence>"
    biological_validation: |
      <what this DOES and does NOT validate>
    pipeline_unblocks: []
  if_primary_tests_fail:
    diagnose: []
    block_downstream: "<one-sentence>"

# 7. LIMITATIONS
limitations:
  - "<explicit out-of-scope claim>"

# 8. IMPLEMENTATION REQUIREMENTS (Build section)
implementation_requirements:
  - id: <req-N-slug>
    kind: listener | parameter_hook | process | data
    title: <short title>
    effort: XS | S | M | L | XL
    description: |
      <what to build>
    steps: []
    defer_until: <study-slug or null>
    unblocks: [<simulation_set/readouts/tests refs>]

# 8b. BIBLIOGRAPHY (renamed from `references:` — v4 reserved)
bibliography:
  expert: [<expert-doc-key>, ...]
  bib_keys: [<bib-key>, ...]

# v3 back-compat shim — legacy DAG-edge form, superseded by the canonical inputs.from (above)
parent_studies: []

# v3 dashboard-managed config (dashboard-v4-reserved shape)
tests:
  auto_discover: true
  data_source: latest_run
  pytest_args: []
  last_results: null
# DEPRECATED: runs[] in study.yaml — runs.db is canonical since F2.
# /pbg-study run-baseline writes to runs_meta + history in the per-study DB.
# The list below is kept only for v3 back-compat reads; do not write to it.
runs: []

# CANONICAL RUNS — declarative recipe for invoking the study's bespoke
# runner scripts (the `sims/run_*.py` pattern used by v2ecoli-style
# workspaces whose runners predate the dashboard-managed baseline /
# variant flow). Optional. /pbg-study run-script <study> [--entry <n>]
# reads this list, picks the default (or named) entry, and shells
# `python <script> <args...>` from the workspace root.
#
# This is a SEPARATE run path from the dashboard-managed baseline /
# variant entries above — those are executed by /api/study-run-baseline
# and /api/study-run-variant, which know how to build the composite
# in-process. canonical_runs are for studies that own their own runner
# script (e.g. division-spanning multi-gen sims, calibration scripts,
# parquet rerun harnesses).
canonical_runs: []
# Example (workspace-root-relative paths so the runner inherits CWD =
# workspace root, where conventions like `out/cache/` resolve):
# canonical_runs:
#   - name: cell-cycle        # required, unique, kebab-case; selected via --entry
#     script: studies/dnaa-01-expression-dynamics/sims/run_baseline.py   # required
#     args: ['4020', '60', 'studies/dnaa-01-expression-dynamics/parquet-runs/cell-cycle.json']  # optional, positional, stringified, no shell interp
#     label: "one cell cycle (4020s @ 60s)"
#     default: true           # optional; first entry wins if none flagged
#   - name: smoke
#     script: studies/dnaa-01-expression-dynamics/sims/run_baseline.py
#     args: ['60', '10', 'studies/dnaa-01-expression-dynamics/parquet-runs/smoke.json']
#     label: "60s @ 10s smoke"

conclusion: null
```

**Sticky-nav ordering (for report renderers).** Per-study sticky nav, in this order:

> Purpose · Pipeline Gate · Simulations · Model Change · Assumptions · Readouts · Tests · Conclusion · Limitations · Requirements · References

Report-generation code that mirrors the dashboard layout should emit headings in that order so authors can navigate report and dashboard interchangeably.

### v4 narrative spine (canonical-optional extensions) {#v4-narrative-spine}

The 8 sections above are the design backbone. The v4 schema (`schema_version: 4`) adds a **second layer of narrative-spine fields** that the v2ecoli dnaa-replication investigation evolved through use, now promoted from "workspace-specific extensions" to canonical-optional. All fields are optional — a v3 spec validates unchanged against the v4 schema — but every new study scaffolded via `/pbg-study new` lands with these fields commented in as TODO placeholders so the user sees the target shape without reading docs.

The narrative spine is grouped into 4 layers. The 6 fields marked ★ are the ones to author first; they render at the top of the report and let a reviewer land on the study without reading the YAML.

**Executive layer** — what a reviewer sees first.
- `title:` — the human **display name** shown everywhere the study appears (Investigation-graph node, study heading, nav). When absent the dashboard derives it from the slug (strips the `<inv>-NN-` ordering prefix, humanizes). The slug stays the technical id. Authored at **Design**; keep it short — it appears in narrow graph cards.
- `claim:` — a **one-line headline of the knowledge the study produced** (what we now believe), shown as the Investigation-graph node's "Finds". When absent the dashboard falls back to the top `findings[].summary`. Authored/refreshed at **Evaluate/Decide** once findings exist.
- `confidence:` — the study's acceptance/confidence state, shown as the Investigation-graph node badge. Enum: `Accepted | Investigating | Planned | Refuted`. When absent it's derived from the 6-axis status (completed/ran→`Accepted`, in_progress/running→`Investigating`, planned→`Planned`, failed/invalid→`Refuted`). Authored explicitly at **Decide** only when the derived value is wrong.
- `runtime:` — per-study execution overrides: `{subprocess_timeout_s, default_emitter: sqlite|xarray, max_generations, post_run_scripts}`. Defaults to workspace settings; populate only what differs.
- **★ `report:`** — the exec summary panel: `{title, verdict, confidence: high|medium|low, evidence_quality: calibrated|literature-matched|aspirational|regression-only, objective, conclusion, main_insight, caveat, key_metrics: [...]}`. `verdict` is free-form (common values: `passing | passing-with-caveats | failing-bio | failing-impl | inconclusive | not-yet-run`).
- **★ `study_card:`** — one-paragraph dashboard card: `{goal, mechanism, why_before_next, expected_result, main_expert_question}`. Distinct from `report.objective` (multi-sentence). `main_expert_question` surfaces in the expert-review panel.

**Framing layer** — what the study is about + how it's configured.
- **★ `question:`** + `assumptions:` — top-level question plus the literature facts the study assumes. Each assumption: `{text, cites: [bib_keys], verified_in_workspace: bool}`.
- **★ `conditions:`** — v4's grouped alternative to top-level `baseline:` + `variants:`: `{baseline: {composite, params}, variants: [...], model_settings: [{name, default, current, range: [low, high], units, cites, notes}], expert_inputs: [...]}`. The `model_settings[]` catalog is the source of truth for tunable parameters — each entry pairs the current value with its default + literature range + citation. `expert_inputs[]` are one-off knobs an expert can twist via the dashboard.
- `enforced_params:` — composite-parameter values the study REQUIRES be applied. Accepts the flat shape `{composite_param: expected_value}` or the wrapped shape `{params: {...}, source: "<bib-key>"}`. The framework's `param_enforcement.check_enforced_params()` verifies after each run that the composite applied the expected values; mismatches surface as `ParamViolation` entries.

**Validation layer** — what would falsify the study.
- **★ `behavior_tests:`** — same 8-section field; the optional `variant:` sub-field on a test scopes it to one named variant (e.g., A/B comparison infrastructure).
- **★ `readouts:`** — same 8-section field; each readout's `store_path` ties an observable to the exact emission path in the composite output.
- `biological_summary:` — multi-paragraph plain-English mechanism prose. The "textbook write-up" a non-modeler would read. Markdown allowed.
- `literature_anchors:` — testable expectations from the literature, paired with their model observable: `[{expectation, model_observable, source, status_in_workspace, cites: [bib_keys]}]`. Lets a reviewer audit "did we implement this?" without reading code. `status_in_workspace` is free-form (common values: `"Not yet measurable" | "Available via X listener" | "Partial" | "Verified — observed value matches"`).

**Implementation + decisions layer** — what got built + what's open.
- `model_change:` — same 8-section field (declarative inventory of code changes).
- `implementation_requirements:` — same 8-section field (TODO list with status + effort + unblocks).
- `design_pivot_required:` — named open decision points: `[{id, status, question, alternatives: [...], requested_response, notes}]`. `status` is free-form (`open | accepted | rejected | superseded-by-<slug> | obsolete | resolved`). Surfaces the choices an expert can weigh in on.
- **★ `conclusion_verdicts:`** — three-track verdict block: `{regression_compatibility: {result: PASS|FAIL|MIXED|PENDING, basis}, biological_validation: {result, basis}, explanatory_gain: {result: POSITIVE|NEUTRAL|NEGATIVE|PENDING, basis}}`. Distinct from `conclusion_logic` (the if-pass/if-fail decision tree). Lets a study be "PASS on regression but MIXED on biology" instead of being forced into one boolean.

**Sibling marker.** `follow_up_of: <slug>` marks a study as a parallel/cleanup follow-up of another (e.g., `dnaa-02f` follow_up_of `dnaa-02`). Distinct from `seeded_from:` (set automatically by `/pbg-study seed-from-followup`) and from `parent_studies:` (which is a DAG dependency).

### v2 narrative spine for Investigations (canonical-optional extensions) {#v2-narrative-spine-investigation}

The investigation schema (`schema_version: 2`) adds a parallel narrative spine that mirrors the per-study spine at a level up. All fields are optional — a v1 spec validates unchanged — but every new investigation scaffolded via `/pbg-investigation new` (or POST `/api/investigation-create`) lands with them commented in as TODOs.

- `executive: {what_is_this, verdict, verdict_status, verdict_detail, decisions_needed: [{question, context}]}` — the **state-first opening** AND the report's Executive summary (single source — keep them in sync). `verdict_status` ∈ `in-progress | passed | complete | blocked | failed | planning`. See [The Investigation graph](#the-investigation-graph-discourse-graph).
- `scientific_argument: {main_claim, evidence_for: [...], evidence_against: [...], key_figures: [...], caveats: [...], interpretation_ref}` — the chain of reasoning, distinct from the bottom-line verdict.
- `biological_story:` — multi-paragraph mechanism prose. The textbook chapter.
- `lead:` — 3-4 sentence front-of-textbook intro (first thing a reader sees, above `biological_story`).
- `at_a_glance: [{study, role}]` — one-line role per member study; lets a reviewer see what each study CONTRIBUTES without opening it.
- `how_to_read:` — evaluator tips ("Read studies in order. Each `report.verdict` is the headline. Open viz only when a primary test fails."). Markdown allowed.
- `glossary: [{term, definition}]` — investigation-local term definitions.
- `guidelines: {literature_anchors, parameter_catalog, calibration_targets, naming_conventions, ...}` — investigation-wide rules every member study respects.
- `inputs: {datasets: [{name, path, supports_claims}], references: [bibkeys], expert_docs: [{name, path}]}` — per-investigation owned inputs, rendered on the Inputs page. `references` bibkeys join the shared `references/papers.bib` for title/link/BibTeX. Dashboard uploads land under `investigations/<slug>/inputs/…` and append here.

The `studies:` list still controls dashboard grouping/visibility; the DAG topology is computed from each member study's canonical `inputs[].from` edges at render time (falling back to the legacy `pipeline_gate.prerequisites:` / `parent_studies:` when a study has not yet migrated).

### Decide-phase follow-up proposals

The Decide phase often surfaces gaps the current study can't close. Those gaps belong as **first-class proposals** on the study itself, then graduate into new sibling studies. Two optional top-level fields make the loop explicit (see [`study.schema.json`](https://github.com/vivarium-collective/pbg-template/blob/main/template/.pbg/schemas/study.schema.json)):

- `followup_proposals:` — list of proposed follow-up studies attached to *this* study.
- `seeded_from:` — provenance stamp on a child study, set automatically when the child is created from a parent's proposal.

**Proposal shape** (terse; per-key meanings mirror the schema):

```yaml
followup_proposals:
  - id: <slug>                  # required, unique within parent study
    title: <short string>       # required
    motivation: |               # required: what gap motivates the followup
      <text>
    hypothesized_mechanism: |   # optional: missing biology/process to add
      <text>
    status: proposed            # proposed | accepted | rejected | seeded
    seeded_study: <slug>        # set when status == seeded
    seed:                       # optional; transferred verbatim at seed time
      purpose:
        question: <text>
        mechanism: <text>
        expected_outcome: <text>
      key_assumptions: [<text>, ...]
      model_change: <object or string>
      simulation_set: []
```

**Seed flow** — `/pbg-study seed-from-followup <parent> <proposal-id>`:

1. Reads `studies/<parent>/study.yaml` and locates `followup_proposals[id == <proposal-id>]` (must be `proposed` or `accepted`).
2. Creates `studies/<new-slug>/study.yaml` with `schema_version: 3`, `phase: Design`, `purpose:` / `key_assumptions:` / `model_change:` / `simulation_set:` populated from `proposal.seed.*` (falling back to `hypothesized_mechanism` for `model_change:` if absent).
3. Auto-adds `pipeline_gate.prerequisites: [<parent-slug>]` (extending any existing `proposal.seed.pipeline_gate`).
4. Stamps `seeded_from: {study: <parent-slug>, proposal_id: <proposal-id>}` on the child. **Pass 10B:** when invoked with `--from-finding <id>`, also stamps `seeded_from.finding: <id>` so the child knows which parent finding motivated it.
5. Flips the parent's proposal entry to `status: seeded` and records `seeded_study: <new-slug>`. **Pass 10B:** when invoked with `--from-finding <id>`, also records `linked_finding: <id>` on the proposal so the finding → proposal → child lineage is queryable from the parent side too.

**Provenance query.** Lineage from a parent study to all its seeded children is a plain grep:

```bash
git grep -n "study: <parent-slug>" -- 'studies/*/study.yaml' | grep seeded_from -B1
```

(or load each `study.yaml` and check `seeded_from.study`). This keeps the lineage discoverable without a separate index file.

#### `discovery_implications` — the richer Decide-phase synthesis

`followup_proposals` (above) is the minimal hook. The **richer, rendered** Decide-phase block is the optional top-level `discovery_implications:` mapping — *"where this study's results leave the mechanism model, and what to investigate next."* The dashboard renders it (the study-detail **Discovery implications** section + the investigation report), and `/pbg-study seed-from-followup` seeds children from its `followup_study_proposals`. All sub-fields optional:

```yaml
discovery_implications:
  resolved_uncertainties: [<text>, ...]      # what this study settled
  remaining_uncertainties: [<text>, ...]     # what is still open
  alternate_hypotheses:                      # competing explanations not yet excluded
    - hypothesis: <text>
      why_plausible: <text>
      mechanism_elements_affected: [<id>, ...]
      discriminating_observables: [<observable>, ...]   # what would tell them apart
  followup_study_proposals:                  # richer variant of followup_proposals
    - id: <slug>
      title: <text>
      motivation: <text>
```

It is **optional and unenforced** — absent → the section is simply omitted (which is why minimal/programmatic studies often lack it). The **rigor scorecard** (`viva_superpowers.rigor`) flags a study that declares neither `discovery_implications` nor `follow_up_studies` with a `next_steps` gap, so the Decide phase is surfaced as feedback without becoming a hard gate.

### Baseline

A study's set of runnable composites — **one or more**. Each entry is a runnable composite document with optional parameter defaults.

- **Shape:** `[{name: <unique-in-study>, composite: <pkg.composites.x>, params: {...}}]` — a **non-empty list**.
- **Why a list:** a study can compare growth across multiple baseline composites side-by-side, not just variants of one.
- **API:** `POST /api/study-baseline-add`, `POST /api/study-baseline-remove`, `POST /api/study-run-baseline {study, composite?}`.
- **Skill:** `/pbg-study baseline-add`, `/pbg-study baseline-remove`, `/pbg-study run-baseline`.

### Variant

A single baseline composite + parameter overrides. Each variant names which composite it derives from via `base_composite`.

- **Shape:** `{name, base_composite: <baseline-entry-name>, parameter_overrides: {...}}`.
- **`base_composite` must reference an existing name in `baseline[]`** — validated server-side; removing a baseline entry that variants depend on returns 409.
- **Scope:** parameter overrides only. Initial-state editing and process/module swaps are deferred.
- **API:** `POST /api/study-variant-add`, `POST /api/study-variant-set-params`, `POST /api/study-variant-delete`, `POST /api/study-run-variant`.
- **Skill:** `/pbg-study variant-add`, `/pbg-study variant-set-params`, `/pbg-study variant-delete`, `/pbg-study run-variant`.

### Intervention

A standalone, text-described experimental condition. Fully separate from variants — no data link in this phase.

- **Shape:** `{name, description}` — `name` is a short slug; `description` is freeform text.
- **API:** `POST /api/study-intervention-add`, `POST /api/study-intervention-update`, `POST /api/study-intervention-delete`.
- **Skill:** `/pbg-study intervention-add`, `/pbg-study intervention-update`, `/pbg-study intervention-delete`.

### Investigation

An Investigation is a **named collection of studies** with an explicit cross-study dependency DAG. Used to group studies that together answer a higher-level research question.

- **On disk:** `<workspace>/investigations/<slug>/investigation.yaml`. Note the filename is `investigation.yaml`, NOT `spec.yaml` — the legacy v2 `investigations/<name>/spec.yaml` files are Studies (auto-migrated to v3) and are excluded by the new iset walker.
- **v1 shape (minimal):** `{schema_version: 1, name, title, status, question, hypothesis, description, studies[], expert_docs[], acceptance_criteria[]}`. `studies` is a list of study slugs (members); `acceptance_criteria` is a list of `{study, behavior}` pairs linking criteria to specific `behavior_tests[].name` entries on member studies.
- **v2 shape (current):** v1 + the 9-section narrative spine: `executive, scientific_argument, biological_story, lead, at_a_glance, how_to_read, glossary, guidelines`. All v2 fields optional. New scaffolds emit v2 (see [v2 narrative spine for Investigations](#v2-narrative-spine-investigation)).
- **API**:
  - `GET /api/iset-list` — summaries (name, title, status, n_studies).
  - `GET /api/iset/<name>` — full investigation + resolved studies (each carrying normalized `parent_studies` for DAG layout).
  - `GET /api/investigation-registry` — cross-worktree view: this server's "current" Investigation + every OTHER live server's `{slug, worktree_path, url, effective_status, pid}`. Powers the left-rail Investigation switcher across worktrees. (Pass C, 2026-05-17.)
  - `POST /api/investigation-create {name, overview?, parent_studies?}` — scaffolds a new investigation. Emits the v2 narrative-spine YAML (via `vivarium_workbench.lib.scaffold_yaml.v2_investigation_scaffold`) with the 9 narrative sections (`executive` / `scientific_argument` / `biological_story` / `lead` / `at_a_glance` / `how_to_read` / `glossary` / `guidelines`) commented in as TODO placeholders.
  - `POST /api/iset-clone {source, target, ...}` — shells out to the workspace's `scripts/clone_investigation.py` (workspace-owned because clone rules are workspace-specific).
  - For update operations (acceptance criteria, narrative-spine field edits) the skills still write YAML directly with atomic tmp-file + rename — `/api/iset-update` is not yet wired.
- **Dashboard render**: Investigations tab cards → DAG canvas on click; rail sidebar groups studies under their investigation header; "Ungrouped" bucket for studies not in any investigation; topological order within each group.
- **Skill**: `/pbg-investigation` for CRUD + scaffold-from-plan + worktree open + cross-study run orchestration (`run <inv-slug>` walks `studies:` and calls `/pbg-study run-script` on each member that has a `canonical_runs:` block; spec-only members are skipped).

> Note: the DAG topology is computed from each member study's `parent_studies:` field at render time. The `studies:` list on the investigation controls visibility/grouping (and the `run` subcommand's execution order) — but per-study `parent_studies` is the authoritative ordering for dependent execution. The orchestrator currently iterates in declared order; a topological-sort mode is a future extension.

#### Investigation ≡ branch ≡ worktree (Pass C, 2026-05-17)

An Investigation slug is also a **git branch name** and a **worktree directory name**. The three are kept in 1:1 correspondence so that parallel agents can each work on a different Investigation without trampling each other's files, runtime DBs (`.pbg/composite-runs.db`), or dashboard ports.

- **`/pbg-investigation new <slug>`** creates `investigations/<slug>/investigation.yaml` AND a git branch `<slug>`, then commits the YAML on that branch. It does NOT push.
- **`/pbg-investigation open <slug>`** creates (or reuses) a worktree at the standard location `<workspace>/.pbg/worktrees/<slug>/` checked out to branch `<slug>`. By default it also boots a per-worktree dashboard server. (`--no-server` skips that.) The standard location keeps worktrees discoverable next to the parent checkout and inside `.pbg/`, which is conventionally git-ignored.
- **One dashboard server per worktree** — intentional. Each worktree has its own runtime state (`.pbg/composite-runs.db`, server log, ports). The server self-registers in `~/.pbg/servers/<name>.<hash>.json` on boot, with `path` set to the worktree (not the parent checkout).
- **Sidebar = cross-worktree switcher.** The left-rail Investigation dropdown queries `/api/investigation-registry`, which fans out across every record under `~/.pbg/servers/*.json` (except its own) to surface their `current` Investigation. Rows for OTHER worktrees are clickable → opens that server's URL in a new tab.
- **Dedup is per-worktree path.** Starting the workbench (`/viva-workbench start`) removes only records that point at the SAME worktree path (after prompting if the PID is still alive). Records at different worktree paths coexist — that's how parallel agents work. `python -m viva_superpowers.workspace_catalog cleanup-servers` removes orphaned records (PID dead OR worktree path missing).

**Known migration note (v2ecoli).** The `dnaa-replication` investigation in v2ecoli was created before this convention, on a branch named `dnaa-replication-studies` (slug-vs-branch mismatch). To bring it into compliance, run `git branch -m dnaa-replication-studies dnaa-replication` on the relevant worktree's checkout, then `/pbg-investigation open dnaa-replication` to materialize it at the standard worktree location.

### The Investigation graph (discourse graph) {#the-investigation-graph-discourse-graph}

The dashboard renders the investigation page as an **Investigation graph**: a discourse/knowledge graph whose nodes are the member studies and whose edges are their `parent_studies` dependencies (see [Study dependencies](#study-dependencies-dag) for the edge `relation:` semantics).

**Mechanism-centered intent.** The investigation's primary artifact is not any single run or chart — it is the *evolving mechanistic understanding* of the biology. Studies are **knowledge-producing operations**: each one generates evidence that updates confidence in elements of that mechanism. The graph makes this legible by reading every node as **Question (Asks) → Evidence (Finds) → Confidence**:

| Node element | Study field | Fallback |
|---|---|---|
| **Asks** | `question:` | — |
| **Finds** | `claim:` | top `findings[].summary` |
| **Confidence** (badge) | `confidence:` ∈ `Accepted \| Investigating \| Planned \| Refuted` | derived from 6-axis status (completed/ran→Accepted, in_progress/running→Investigating, planned→Planned, failed/invalid→Refuted) |
| Display name | `title:` | slug, prefix-stripped + humanized |
| Edge | `parent_studies[].relation:` ∈ `leads-to \| regulatory \| supports \| refutes` | `leads-to` (solid edge; `regulatory`/`refutes` dashed) |

All five are study-level — authored via `/pbg-study` (`title:` + `relation:` at Design; `claim:` + `confidence:` at Evaluate/Decide). See [pbg-study → Investigation-graph fields](../../skills/pbg-study/SKILL.md).

**State-first opening.** The investigation opening is rendered from the investigation's `executive:` block (`{what_is_this, verdict, verdict_status, verdict_detail, decisions_needed:[{question, context}]}`) — and that **same block** is the single source for the report's Executive summary (do not maintain a second copy). `verdict_status` ∈ `in-progress | passed | complete | blocked | failed | planning`. The per-study `confidence:` badges roll up into the investigation `verdict` / `verdict_status`; keep the two consistent.

### Study dependencies (DAG)

Studies can declare ordering via the optional `parent_studies:` field. Each entry is either a bare slug (legacy, normalized to `{study, condition: tests-passed}`) or an object `{study: <slug>, condition: tests-passed | ran | complete, relation?: leads-to | regulatory | supports | refutes}`. Conditions:

- `tests-passed` — parent's `tests.last_results.passed > 0` AND `failed == 0`.
- `ran` — parent's `status` is one of `{ran, complete}`.
- `complete` — parent's `status == complete`.

The optional `relation:` carries the **discourse semantics** of the edge in the [Investigation graph](#the-investigation-graph-discourse-graph), independent of the gating `condition`. Enum: `leads-to` (default) `| regulatory | supports | refutes`. The graph renders `leads-to` / `supports` as solid edges and `regulatory` / `refutes` as dashed edges. Author the relation when declaring a dependency to express *why* one study follows another, not just *that* it does.

**API**: `GET /api/investigations` returns each study with computed `parent_studies` (normalized to object form), `blocked: bool`, and `blocked_by: [{study, condition, missing-diagnostic}]`. A parent that doesn't resolve to a known study slug surfaces as `parent-not-found` in `blocked_by`.

**Dashboard rendering**: the Studies tab's `Dependencies` sort (default) topologically orders studies — roots first, alphabetical within depth. Each card shows:

- `Depends on: <links> (<condition>) · ...` (blue, clickable).
- `Blocks: <links> · ...` (grey, clickable).
- `🔒 blocked` status pill with the `blocked_by` diagnostics in tooltip, when `blocked: true`.

### Run

A completed execution of a baseline composite or variant. The dashboard records run metadata; the actual simulation trace lives in `runs.db` (per study).

- **Shape:** `{run_id, variant: <name|null>, composite: <baseline-entry-name>, label, status, n_steps}`. `variant: null` indicates a baseline run.
- **API:** `POST /api/study-run-baseline {study, composite?}`, `POST /api/study-run-variant {study, variant}`, `POST /api/study-run-delete`, `POST /api/study-runs-clear`, `POST /api/study-comparison-add {study, run_ids}`.
- **Skill:** `/pbg-study run-baseline`, `/pbg-study run-variant`.
- **SimulationsDB tagging convention.** For a run to surface in SimulationsDB tagged to its study + investigation, its emitter output must live under the per-study path `studies/<slug>/parquet-runs/<run>/` (ParquetEmitter hive) or `studies/<slug>/runs.db` (SQLite, with `emitter_path` recorded). The dashboard-managed baseline/variant flow already writes there; **bespoke `canonical_runs:` runners must write there too** or their runs won't be tagged.

#### Canonical run recipe (bespoke scripts)

Some workspaces (notably v2ecoli's `sims/run_dnaa_*.py` family) ship runner scripts that predate the dashboard's baseline/variant flow — division-spanning multi-gen sims, calibration harnesses, parquet rerun wrappers. They don't fit the in-process composite executor, so the dashboard can't invoke them via `/api/study-run-baseline`.

The `canonical_runs:` block on a study.yaml declares "here is how you re-run me" for those scripts:

```yaml
canonical_runs:
  - name: cell-cycle
    script: studies/dnaa-01-expression-dynamics/sims/run_baseline.py
    args: ['4020', '60', 'studies/dnaa-01-expression-dynamics/parquet-runs/cell-cycle.json']
    label: "one cell cycle (4020s @ 60s)"
    default: true
  - name: smoke
    script: studies/dnaa-01-expression-dynamics/sims/run_baseline.py
    args: ['60', '10', 'studies/dnaa-01-expression-dynamics/parquet-runs/smoke.json']
    label: "60s @ 10s smoke"
```

- **Shape:** list of `{name, script, args?, label?, default?}`. `script` is a path relative to the workspace root; `args` are positional, stringified (no shell interpolation). Exactly one entry should be `default: true`; if none is, the first wins.
- **No dashboard API.** This is a pure shell-out flow; the skill reads the YAML and execs `python <script> <args...>` from the workspace root.
- **Skill:** `/pbg-study run-script <study> [--entry <name>] [--list]`.
- **When to use it:** the runner is a hand-written script that owns its own composite construction and emitter wiring. When the runner can be expressed as a composite + `parameter_overrides`, prefer `run-baseline` / `run-variant` instead — the dashboard then surfaces the run in `runs.db` automatically.

### Visualization

A named visualization config attached to a study. Renders run output to HTML.

- **Shape:** `{name, address, config}`. `address` is a dotted reference to a `Visualization` (a `Step` subclass — see `docs/conventions/visualizations.md`).
- **API:** `POST /api/study-viz-add` (alias `/api/investigation-add-viz`), `POST /api/study-viz-render`.
- **Skill:** `/pbg-viz`.

#### Provenance & freshness {#viz-provenance-freshness}

Every `visualizations[]` entry may declare an optional `render:` command string. When present, `/pbg-study refresh-viz` (and the auto-refresh that fires after a successful `run-baseline` / `run-variant` / `run-script`) uses it to regenerate the chart against the latest run.

**`runs.db` as the authoritative run↔study record.** Each study's `runs.db` (SQLite) holds a `runs_meta` table that is the single source of truth for run provenance: `run_id`, `started_at`, `completed_at`, `composite`, `variant`, `emitter_path`, and `generation_id`. `viva_superpowers.run_registry.latest_run(runs_db_path)` returns the most-recently-completed row; `refresh-viz` queries it before every invocation.

**`visualizations[].render` contract.** `render:` is a shell command run with `cwd` = the study directory. Two substitutions happen before execution:

- `{chart}` in the command string is replaced with the entry's `chart:` path (relative to the study dir).
- Two environment variables are injected: `PBG_RUN_DIR` (absolute path to the run's emitter store) and `PBG_RUN_ID` (the run's UUID from `runs_meta`).

Example entry:

```yaml
visualizations:
  - name: dnaa3_binding_analysis
    chart: charts/dnaa3_binding_analysis.svg
    render: "python scripts/render_dnaa3_binding_analysis.py --out {chart}"
```

**`<chart>.meta.json` sidecar.** After each successful render, `refresh_study_viz` stamps a JSON sidecar alongside the chart file:

```json
{
  "source_run_id": "<uuid from runs_meta>",
  "generation_id": "<generation counter>",
  "rendered_at": "<ISO-8601 timestamp>",
  "command": "<render command after substitution>",
  "content_hash": "<sha256 of the chart file>"
}
```

**Freshness states.** A chart is in one of four states:

| State | Meaning |
|---|---|
| `fresh` | On-disk chart exists; sidecar `source_run_id` == latest run id |
| `stale` | On-disk chart exists; sidecar `source_run_id` != latest run id (run advanced) |
| `untracked` | On-disk chart file exists but has no matching `visualizations[]` entry |
| `unrendered` | `visualizations[]` entry exists but no chart file on disk yet |

**`refresh-viz` behavior.** `/pbg-study refresh-viz <slug>` (and `/pbg-investigation refresh-viz <inv-slug>`) re-runs each entry's `render:` command and updates the sidecar. Entries without a `render:` command report `needs_manual_refresh` and are left in place. The `run-baseline`, `run-variant`, and `run-script` subcommands invoke `refresh-viz` automatically after a successful run; pass `--no-refresh-viz` to suppress.

## The dashboard server (read surface)

Skills that read dashboard state do so via these HTTP endpoints:

| Endpoint | Returns | Used by |
|---|---|---|
| `GET /api/investigations` | All studies with summary fields (`name, status, baseline_names, n_baseline, n_variants, n_interventions, n_runs, baseline_source, conclusions_excerpt`) | `/pbg-catalog list` |
| `GET /api/workspace-manifest` | Composites, studies, registry, health | `/pbg-status`, `/pbg-catalog list` |
| `GET /api/investigation-composites?investigation=<n>` | A study's baseline list as `[{name, source, params}]` | `/pbg-study`, UI |
| `GET /api/composite-resolve?id=<id>&overrides=<json>` | A composite's `{parameters, state, svg, kind, ...}` for param-form pre-fill | `/pbg-explore`, UI |
| `GET /api/composites` | Workspace catalog of discoverable composites | `/pbg-catalog list` |

## The dashboard server (write surface)

| Endpoint | Body | Skill subcommand |
|---|---|---|
| `POST /api/study-set-objective` | `{study, text}` | `/pbg-study set-objective` |
| `POST /api/study-set-conclusion` | `{study, text}` | `/pbg-study set-conclusion` |
| `POST /api/study-baseline-add` | `{study, name, composite, params?}` | `/pbg-study baseline-add` |
| `POST /api/study-baseline-remove` | `{study, name}` | `/pbg-study baseline-remove` |
| `POST /api/study-run-baseline` | `{study, composite?, steps?}` | `/pbg-study run-baseline` |
| `POST /api/study-variant-add` | `{study, name, base_composite, parameter_overrides?}` | `/pbg-study variant-add` |
| `POST /api/study-variant-set-params` | `{study, variant, parameter_overrides}` | `/pbg-study variant-set-params` |
| `POST /api/study-variant-delete` | `{study, variant}` | `/pbg-study variant-delete` |
| `POST /api/study-run-variant` | `{study, variant, steps?}` | `/pbg-study run-variant` |
| `POST /api/study-intervention-add` | `{study, name, description?}` | `/pbg-study intervention-add` |
| `POST /api/study-intervention-update` | `{study, name, description}` | `/pbg-study intervention-update` |
| `POST /api/study-intervention-delete` | `{study, name}` | `/pbg-study intervention-delete` |
| `POST /api/study-viz-add` | `{study, name, address, config}` | `/pbg-viz` |
| `POST /api/composite-test-run` | `{id, steps, emit_paths?}` | `/pbg-run` |

## Skill ↔ concept map

| Skill | Reads | Writes | Notes |
|---|---|---|---|
| `/pbg-init` | — | Workspace | Scaffolds new workspace. |
| `/viva-workbench` | `.pbg/server/server-info` | Starts/stops the dashboard (workbench) server. | Required precondition for every other dashboard-touching skill; also serves reports. |
| `/pbg-catalog [list]` | Workspace, Composites, Studies | — | Read-only catalog. |
| `/pbg-catalog install <pkg>` / `/pbg-catalog uninstall <pkg>` | Workspace | Workspace deps | Wraps `pip install` + workspace catalog. |
| `/pbg-status` | Workspace state | — | Server up? recent activity? Probes the running workbench server directly. |
| `/pbg-expert <tool>` | External Process | Sibling `pbg-<tool>/` repo | Wraps a simulator as a Process. Default mode creates a sibling repo + tests + README + report; `--lightweight` writes a single file into the current workspace package instead. |
| `/pbg-expert <name> <tools…>` | Composite catalog | Sibling `pbg-<name>-composite/` repo | Composes installed wrappers. `--lightweight` writes a single composite file into the workspace package instead. |
| (internal) `/pbg-suggest <id>` | `.pbg/agent-requests/<id>.json` | `.pbg/agent-responses/<id>.json` | Dashboard "Suggest" callback. Not user-facing. |
| (maintainer) `scripts/audit-pbg-repo.py <repo>` | External pbg-* repo | — | Audits packaging/discovery conventions. Replaces v0.8 `/pbg-package`. |
| `/pbg-explore` | Composite | Dashboard view | Opens composite in dashboard. |
| `/pbg-run` | Composite | Run record | Runs a composite directly (no Study). |
| `/pbg-study` | Study | Study | **All Study CRUD + runs.** See subcommand table above. |
| `/pbg-investigation` | Investigation | Investigation YAML | **All Investigation CRUD + scaffold-from-plan.** Writes YAML directly (no write endpoints yet). |
| `/pbg-viz` | Visualization | Visualization | Adds a viz to a study. |
| `/pbg-report` | Study | Report file | Renders study summary to markdown. |
| `/pbg-workspace` | Workspace | Workspace state | Workspace-level commands. |

## Pass A — multi-axis status, finding provenance, dependency hashes {#pass-a}

> **Status:** Pass A of the infrastructure-feedback roadmap. Schema lives in
> [`study.schema.json`](https://github.com/vivarium-collective/pbg-template/blob/main/template/.pbg/schemas/study.schema.json);
> dashboard surface in [vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench).
> Sweep tables · linting · scaffold tracking · failure modes · expert questions ·
> dashboard filters · claim-traceability view · JSON bundle export come in later passes.

Three orthogonal additions on `study.yaml`. **All new fields are optional**, so
v3 studies that set only the legacy `status:` continue to validate and render
unchanged.

### Multi-axis status {#multi-axis-status}

Six independent status axes replace the single coarse-grained `status:` field
for new specs. Each axis tracks one dimension of a study's lifecycle and is
nullable.

| Axis                    | Enum values                                                          |
|-------------------------|----------------------------------------------------------------------|
| `design_status`         | `planned · drafted · expert_reviewed · approved`                     |
| `implementation_status` | `not_started · partial · complete`                                   |
| `simulation_status`     | `not_run · running · ran · failed`                                   |
| `evaluation_status`     | `not_evaluated · evaluated · failed_evaluation`                      |
| `gate_status`           | `blocked · needs_calibration · passed · failed · stale`              |
| `expert_review_status`  | `not_requested · requested · reviewed · approved · disputed`         |

```yaml
design_status: drafted
implementation_status: partial
simulation_status: ran
evaluation_status: not_evaluated
gate_status: needs_calibration
expert_review_status: requested
```

**Dashboard rendering** (Pass A):

- **Headline pill priority** on the study-detail page:
  1. If `gate_status` is set, render it as the headline pill, colored per
     `blocked=gray · needs_calibration=amber · passed=green · failed=red · stale=purple`.
  2. Else if the legacy single `status:` is set, render it (existing behavior).
  3. Else fall back to `planned`.
- **Status detail panel** below the header: one chip per axis that is set;
  rows for unset axes are hidden. The panel itself is hidden when none of the
  six axes are set, so legacy studies look identical to before.
- **Iset endpoint passthrough**: `GET /api/iset/<name>` surfaces all six
  axes per member study (`None` when unset) so future Investigation-level
  rollups can aggregate them.

The legacy `status:` field stays in the schema for back-compat and is the
field the dashboard's existing `effective_status` derivation reads from. The
new axes are additive; they do not (yet) feed the existing derivations.

### finding_provenance {#finding-provenance}

The `findings:` array (proposed in
[`2026-05-16-findings-protocol.md`](https://github.com/vivarium-collective/v2ecoli/blob/main/docs/superpowers/notes/2026-05-16-findings-protocol.md))
is formally added to the schema as an optional top-level array. Each entry
requires `id` (kebab-slug) and `statement` (English claim); the full structure
(`kind`, `evidence`, `expected`, `expert_reference`, `next_action`, …) is
still being worked out across passes, so the entry is `additionalProperties:
true` — authors can include whichever fields the protocol calls for without
re-versioning the schema.

Each finding may carry a `provenance:` object with everything needed to
reproduce it. All sub-fields optional — populate what you have.

```yaml
findings:
  - id: F-02
    statement: |
      Autorepression of DnaA is missing in v2ecoli's transcription model.
    provenance:
      run_ids: [run-001, run-002]
      simulation_config_hash: sha256:abc...
      model_commit_hash: deadbeef
      parca_cache_hash: sha256:def...
      random_seeds: [0, 1, 2]
      analysis_script: scripts/measure_autorepression.py
      evaluator_version: v0.4.1
      raw_data_artifact: runs.db
      metric_table_artifact: out/metrics.csv
```

**When to populate.** A finding is *reproducible* once `provenance` lets a
fresh checkout regenerate it: at minimum a `model_commit_hash` + one of
`raw_data_artifact` / `analysis_script`. Without provenance, a finding is a
claim with no audit trail — a later pass will surface this in a linter.

### Findings protocol (Pass 10A) {#findings-protocol-pass-10a}

Pass 10A formalizes the `findings:` shape introduced in Pass A. The
authoritative spec is
[`2026-05-16-findings-protocol.md`](https://github.com/vivarium-collective/v2ecoli/blob/main/docs/superpowers/notes/2026-05-16-findings-protocol.md);
this section is a one-paragraph summary plus a tooling map.

**Shape.** Each finding still requires `id` + `statement`; Pass 10A adds
two more required enums — `kind` ∈ {biological | computational | methodological}
and `status` ∈ {confirms | partial | contradicts | novel}. The four optional
sub-objects `evidence`, `expected`, `expert_reference`, and `provenance`
remain `additionalProperties: true` so authors can extend them per study.
Plus `explanation` (multi-paragraph rationale), `next_action` (concrete
one-liner), and `obsoleted_by` (chain to a superseding finding).

```yaml
findings:
  - id: F-01
    kind: biological
    status: contradicts
    statement: |
      v2ecoli's baseline emits ~115 DnaA/cell — 5x below the literature band.
    evidence:
      from_run: baseline-heavy-tf
      from_test: dnaA-count-in-range
      observed: 115
      units: molecules/cell
    expected:
      cites: [Schmidt2016NatBiotechnol, Sekimizu1991JBacteriol]
      range: [300, 800]
      summary: "Mass-spec puts DnaA at 300-800 copies/cell."
    expert_reference:
      doc: chromosome_replication_plan
      section: "§2.1"
      note: "Plan lists 'DnaA per-cell count' as a layer-1 sanity check."
    explanation: |
      Shortfall is consistent across timepoints — likely EG10235 TE miscalibration.
    next_action: Seed calibration_task follow-up.
```

**Five tooling components.** All five components now ship: A, B, C in
Pass 10A and D, E in Pass 10B.

| Component | Status | Where |
|---|---|---|
| A. `/pbg-study findings` interactive walk | shipped (10A) | `skills/pbg-study/SKILL.md` → `viva_superpowers/study_findings.py` |
| B. `search_expert_docs()` helper | shipped (10A) | `viva_superpowers/expert_search.py` |
| C. Findings linter | shipped (10A) | `viva_superpowers/report_linter.py` (4 new checks) |
| D. Cross-study findings index on `/pbg-report` | shipped (10B) | `viva_superpowers/report.py:render_workspace_findings_index` → `reports/findings.html` |
| E. Findings-aware `seed-from-followup` | shipped (10B) | `skills/pbg-study/SKILL.md` `--from-finding <id>` → `viva_superpowers/seed_from_followup.py` |

The four new linter checks (C):

  - `decide_phase_missing_findings` (error) — study reached Decide/Evaluated with zero findings[].
  - `finding_without_evidence` (warning) — biological/computational finding with no `evidence.from_run` and no `evidence.from_test`.
  - `finding_cites_unknown_bib_key` (error) — `expected.cites[]` entry not in `references/papers.bib`.
  - `finding_references_unknown_expert_doc` (error) — `expert_reference.doc` not in `workspace.yaml.expert_docs[]`.

All four plug into the existing `/pbg-report --lint` override mechanism.

#### Pass 10B additions

**D. Cross-study findings index.** `/pbg-report` now writes a second
workspace-level page at `reports/findings.html` alongside
`reports/index.html`. It harvests every `findings[]` entry across every
`studies/*/study.yaml` and renders them grouped by `status` (default
view: confirms / partial / contradicts / novel) or by `kind` (toggle
button: biological / computational / methodological). Filter chips at
the top let the reader narrow by status + kind interactively (small
client-side JS, no framework). Each row shows the finding id, the
parent study slug (linked to the per-study report when one exists), a
one-liner cut of the statement (full text in a `<details>` disclosure),
status + kind badges, plus small chips for any `expected.cites` bib_keys
and the `expert_reference.doc`. Empty workspaces render a friendly
"No findings recorded — run `/pbg-study findings <slug>` to start"
panel so the link from the dashboard never 404s. The workspace
dashboard (`reports/index.html`) gains a "Findings index" panel that
links to the page and badges the total count.

**E. Findings-aware `seed-from-followup`.** The Pass 8
`/pbg-study seed-from-followup <parent> <proposal-id>` subcommand takes
an optional `--from-finding <finding-id>` flag. When passed, the helper
at `viva_superpowers/seed_from_followup.py` reads the finding off the
parent and pre-populates the child's `purpose:` + `key_assumptions:`
from `next_action` / `explanation` / `evidence.smoking_gun` (mapping
documented in `skills/pbg-study/SKILL.md` and the helper's docstring).
The child gets `seeded_from.finding: <id>` (Pass 10B schema extension,
see [`study.schema.json`](https://github.com/vivarium-collective/pbg-template/blob/main/template/.pbg/schemas/study.schema.json))
and the parent's proposal entry gets `linked_finding: <id>`, so the
finding → proposal → child-study lineage is queryable from both
directions:

```bash
# All children seeded from any finding on parent dnaa-01:
grep -rA2 "seeded_from:" studies/*/study.yaml | grep -B1 "study: dnaa-01" | grep finding
# All proposals on dnaa-01 that link back to a finding:
yq '.followup_proposals[] | select(.linked_finding) | {id, linked_finding}' studies/dnaa-01/study.yaml
```

### Dependency-with-hashes ({#dependency-with-hashes})

`pipeline_gate.prerequisites` items already accept (a) a bare slug string or
(b) `{study, condition: tests-passed | ran | complete}`. Pass A extends the
object form with three new optional fields that let downstream studies declare
*which* upstream outputs they consume and *which* artifact hashes they were
last validated against. Both legacy forms continue to validate.

```yaml
pipeline_gate:
  prerequisites:
    - study: dnaa-01-expression-dynamics
      condition: tests-passed            # existing
      required_gate_status: passed       # NEW: min gate_status the parent must reach
      outputs_used:                       # NEW: named outputs this study consumes
        - autorepression_signal
        - dnaA_steady_count
      artifact_hashes:                   # NEW: parent artifact hashes validated against
        model_commit: deadbeef
        parca_cache: sha256:abc...
        analysis_script: null
```

**Semantics.**

- `required_gate_status` ANDs with `condition`: both must hold for the
  dependency to count as satisfied.
- `outputs_used` lets the linter detect over-broad deps and lets the dashboard
  draw targeted dataflow edges instead of one fat "depends on" arrow.
- `artifact_hashes` enables **stale propagation**: when a parent regenerates
  an artifact whose hash diverges from the value recorded here, the dashboard
  flips this study's `gate_status` to `stale`. The matching axes are intended
  to mirror `finding_provenance.{model_commit_hash, parca_cache_hash,
  analysis_script}` so the same hashes flow up the dependency graph.

## v4 reserved field names {#v4-reserved-fields}

Schema v4 (the current dashboard validation target) reserves these top-level
field names on `study.yaml`. **If you author v3 specs (the common case) with
fields that share these names but a different shape, the v3→v4 auto-migration
will collide and surface validation errors.**

| Field | Required shape (v4) | Notes |
|---|---|---|
| `tests` | object: `{auto_discover: bool, data_source: enum, pytest_args: list, last_results: object\|null}` | The dashboard runs pytest from `studies/<slug>/tests/` and writes results back here. |
| `references` | list of `{file: str, section?: str}` objects | Resolves to markdown / PDF docs. |
| `implementation_tasks` | string (markdown blob) | Narrative; not parsed. |

**If you have a custom field with one of these names but a different shape,
rename your custom field.** Common renames the team has adopted:

- `references:` (dict) → `bibliography:`
- `implementation_tasks:` (list of strings) → `tasks:`

If your spec is intentionally v4-shape, set `schema_version: 4` at the top
level so the migration short-circuits and you get the v4 validator directly.

When a collision occurs, the validation error message now includes a `Note:`
suffix naming the reserved field, so you know to rename your custom field
rather than guessing at a shape mismatch.

## Study lint checks (`/pbg-report`) {#study-lint-checks}

`/pbg-report`'s structural lint (Pass B) warns on common empty-field gaps in
`studies/<slug>/study.yaml` so a study card isn't half-blank. The check ids
below are the literal `check=` values emitted by
`viva_superpowers.report_linter`; the field set + enum values themselves are
defined by [`study.schema.json`](https://github.com/vivarium-collective/pbg-template/blob/main/template/.pbg/schemas/study.schema.json)
(see the [multi-axis status](#multi-axis-status) table for the status enums).
**All of these are non-blocking** — a study still passes lint with them; they
mark the gap for the next scaffolding pass.

| Check id | Field(s) | Triggers when |
|---|---|---|
| `missing_baseline` | `baseline` or `conditions.baseline` | both absent |
| `missing_variants` | `variants` or `conditions.variants` | both absent / empty |
| `missing_conditions_block` | `conditions:` (v4) | absent AND no `model_change` / `implementation_requirements` |
| `missing_simulation_set` | `simulation_set:` | absent / empty |
| `missing_planned_runs` | `planned_runs:` / `runs:` | both absent |
| `missing_readouts` | `readouts:` | absent / empty |
| `missing_visualizations` | `visualizations:` | absent / empty |
| `missing_provenance` | a finding's `provenance:` | a `findings[]` entry has no provenance object |
| `status_legacy_only` | multi-axis status axes | only the legacy `status:` is set |
| `dag_edges_legacy_only` | `pipeline_gate:` | only the legacy `parent_studies:` is set |
| `narrative_spine_completeness` | v4 narrative-spine sections | info-level nudge per missing section |

To scaffold a complete study, fill (in rough order): multi-axis status +
`pipeline_gate`, `conditions.baseline.composite`, a `simulation_set` entry per
planned variant, `readouts`, `behavior_tests`, and at least one
`visualizations` entry — re-running `/pbg-report` until the warnings clear.

## Migration notes

- **v2 → v3 on read:** `vivarium_workbench.lib.spec_migration.migrate_v2_to_v3` runs automatically in `load_spec`. Skills never need to invoke it.
- **v2 endpoints still aliased:** `/api/investigation-add-viz`, `/api/investigation-render-viz`, and a few others remain as aliases of their `/api/study-*` v3 counterparts. New skill code should prefer the `study-` form.
- **Removed in v3:** `/api/study-set-baseline-params` (covered by `study-variant-set-params` + the new baseline-list shape); `/api/investigation-set-overview` (split into `set-objective` + status writes).

## Out of scope (deferred)

- Variant scope beyond parameters (initial-state edits, process swaps).
- Linking interventions to variants/runs (currently text-only).
- Stored-data cleanup of the per-variant nested `intervention` field on disk (the v3 migration drops it in-memory; the field may persist in on-disk v2 specs).

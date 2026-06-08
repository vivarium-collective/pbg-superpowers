---
name: pbg-study
description: Manage Studies in the dashboard — organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide). Full CRUD for baseline composites, variants, interventions, runs, and conclusions. Wraps the v3 /api/study-* endpoints.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: new <name> <composite>|fill-overview|set-objective|baseline-add|baseline-remove|variant-add|variant-set-params|variant-delete|intervention-add|intervention-update|intervention-delete|verify|preview-viz|run-baseline|run-variant|run-script|refresh-viz|clean|set-conclusion|set-verdicts|add-literature-anchor|add-pivot|add-requirement|findings|propose-followup|seed-from-followup [--from-finding F-NN]|open [args]
---

# pbg-study

The end-to-end interface for **Studies** in the vivarium-dashboard, organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide; see [`docs/concepts/vivarium-dashboard-model.md`](../../docs/concepts/vivarium-dashboard-model.md#study-lifecycle)).

## Layout (investigation-centric, nested)

Studies live **nested under their investigation**:
`investigations/<inv>/studies/<slug>/study.yaml`, each carrying an `investigation: <inv>`
back-ref. The investigation's publication/report lives at `investigations/<inv>/reports/`
(per-investigation — there is **no global repo-wide report**).

- **Resolve a study dir** (nested- and flat-aware): `python -m pbg_superpowers.paths --study <slug>`.
- **Create a new study** under `$INVESTIGATIONS_DIR/<inv>/studies/<slug>/` (write the `investigation:` back-ref).
- Legacy flat `studies/<slug>/` still resolves (back-compat) until a repo is migrated with `pbg-migrate-nested`.

This block governs the paths below: where older text says `studies/<slug>/` or `$STUDIES_DIR/<slug>/`, prefer the resolver / the nested path.


A Study is a self-contained research unit holding one-or-more baseline composites, variants (parameter perturbations), interventions (text-described conditions), runs, and visualizations. The **Build** phase between Design and Simulate doesn't have pbg-study subcommands directly — it's handled by `/pbg-expert` (heavy mode → sibling repo) or `/pbg-expert --lightweight` (in-workspace, single-tool or composite form), or by hand-edited code in `pbg_<workspace>/processes/`.

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`. Fail if not found.
2. Read `.pbg/server/server-info` for the dashboard URL. If absent, fail with: "Run `/pbg-server start` first."

## Tests on a Study (v4 schema)

A v4 Study has a `tests/` subdirectory containing pytest files. The dashboard
runs them via `POST /api/study-tests-run {study}` and writes a summary back to
`study.yaml.tests.last_results`. The Tests tab on the Study detail page shows
per-test pass/fail with expandable tracebacks.

Tests use a `run` pytest fixture provided by `vivarium_dashboard.testing`:

```python
# studies/<slug>/tests/conftest.py
from vivarium_dashboard.testing import run  # noqa: F401

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

## Cross-study dependencies (parent_studies)

A study can declare ordering against other studies in the workspace via
the optional `parent_studies:` field. Each entry is either a bare slug
or an object `{study, condition}` where `condition` is one of
`tests-passed` | `ran` | `complete` (default `tests-passed` when omitted).

```yaml
# studies/dnaa-02-atp-hydrolysis/study.yaml
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
| `parent_studies[].relation:` | edge semantics on a dependency | solid edge (`leads-to`) or dashed edge (`regulatory` / `refutes`); `supports` reinforces | `leads-to` | **Design** |
| `claim:` | one-line headline of the knowledge the study produced (what we now believe) | the node's "Finds" line | top `findings[].summary` | **Evaluate / Decide** |
| `confidence:` | the study's acceptance/confidence state | node badge | from 6-axis status: completed/ran→`Accepted`, in_progress/running→`Investigating`, planned→`Planned`, failed/invalid→`Refuted` | **Decide** (when the derived value is wrong) |

**Enums.**

- `confidence:` ∈ `Accepted | Investigating | Planned | Refuted`.
- `parent_studies[].relation:` ∈ `leads-to` (default) `| regulatory | supports | refutes`. Renders solid for `leads-to`, dashed for `regulatory` / `refutes`. Author the relation when declaring a dependency to express the discourse relationship, not just ordering.

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
`relation:`) are naturally authored at **Design** time — `/pbg-study new`
scaffolds the study, then add the `title:` line and wire `parent_studies` with
relations as you declare dependencies (these are YAML-direct; no dedicated POST
endpoint). `claim:` and `confidence:` belong to **Evaluate/Decide** — refresh
`claim:` once `findings:` exist (after `/pbg-study findings`), and set
`confidence:` explicitly at Decide (alongside `/pbg-study set-verdicts`) only
when the value derived from the 6-axis status is wrong.

## Grouping studies into Investigations

Studies that share a research arc can be grouped into an **Investigation** (a named collection with its own question/hypothesis + acceptance criteria). Studies don't declare investigation membership themselves; the investigation lists them in its `studies:` field. Use `/pbg-investigation` for investigation CRUD and the `scaffold-from-plan` marquee command that auto-generates an investigation + all constituent studies from a plan PDF.

## Reference / mechanism discipline: NEVER silently add what the expert did not provide

When you cite a paper (`--cite`, `--source`, `cites:`, `literature_anchors[].source`) or lean on a mechanism, that reference/mechanism must be one the **expert actually provided or explicitly approved**. If, while building or evaluating a study, you reach for a paper, parameter, or mechanism the expert did **not** give you, do **not** quietly fold it into `cites:` / `literature_anchors` / the prose as if it were sanctioned. Record it on the parent **investigation** under `proposed_inputs:` with `status: pending`, a `provenance` (which commit / why it surfaced), and a `rationale` (what you used it for), and let the expert Accept or Decline it in the report. On Accept, a `kind: reference` item is promoted into the investigation's `inputs.references` and becomes a real provided reference (then it is fair to cite); a `kind: mechanism` item is marked accepted for a human to integrate. On Decline it is left out. See the `proposed_inputs:` schema in **pbg-investigation**. This guardrail keeps outside claims from entering the record as expert-sanctioned.

## Sub-commands

### Design subcommands

#### `new <composite-id>`

Create a new Study seeded with one baseline composite. The dashboard's seed endpoint writes a **v4-shape `study.yaml`** with the 14-section narrative spine commented in as TODO placeholders (the same shape the v2ecoli dnaa-replication investigation evolved through use):

- **Executive layer** — `runtime` · ★ `report` · ★ `study_card`
- **Framing layer** — ★ `question` + `assumptions` · ★ `conditions` (baseline + variants + model_settings) · `enforced_params`
- **Validation layer** — ★ `behavior_tests` · ★ `readouts` · `biological_summary` · `literature_anchors`
- **Implementation + decisions** — `model_change` · `implementation_requirements` · `design_pivot_required` · ★ `conclusion_verdicts`

★ sections are the ones to author first — they render at the top of the rendered study page. All v4 fields are optional per `study.schema.json`, so the scaffold is lint-clean on day one and the user opts in by uncommenting + filling sections. See `template/NEXT_STEPS.md` in pbg-template for the full walking guide.

POST `/api/investigation-create` (legacy route name; aliased to `/api/study-create`):

```json
{"name": "<study-name>", "source": "<composite-id>"}
```

Returns the new study's name + URL. Print and offer to open it via `/pbg-study open <name>`. After scaffolding, the immediate next step is `/pbg-study fill-overview <slug>` to draft the question/hypothesis/objective fields, then uncomment the ★ sections in the YAML and fill them as you build.

#### `fill-overview <slug> [--from-plan <path>] [--from-expert <path>...] [--fields <comma-list>] [--dry-run]`

Draft the `question`, `hypothesis`, `objective`, and/or `description` fields of an existing study by reading its linked plan and expert documents, then write them via the API after user confirmation.

**Arguments:**

- `<slug>` (required) — study slug under `studies/<slug>/`. Abort with a clear error pointing at `/pbg-study new` if the directory or `study.yaml` is absent.
- `--from-plan <path>` (optional) — path to a planning PDF or markdown that decomposes the study's intent. If absent, look inside `references/expert/` for a file whose name matches `<slug>` or contains the word "plan".
- `--from-expert <path>` (optional, repeatable) — additional expert-knowledge PDFs or markdown files. If absent, consult `workspace.yaml.expert_docs` and use any entry whose `claims_supported` list overlaps with the study's `parent_studies` or `id`.
- `--fields <comma-list>` (optional) — restrict drafting to a subset. Default fields: `question,hypothesis,objective,description`. v4 narrative fields are opt-in via `--include-narrative` (see below) or by naming them explicitly: `report,study_card,biological_summary`.
- `--include-narrative` (optional) — extend the default draft set with the v4 narrative-spine fields: `report` (verdict + confidence + evidence_quality + main_insight + caveat), `study_card` (goal + mechanism + why_before_next + expected_result + main_expert_question), `biological_summary` (multi-paragraph mechanism prose). Drafted from the same plan + expert PDFs.
- `--dry-run` (optional) — print the proposed diff and stop without writing anything.

**Behavior (steps Claude follows when running this subcommand):**

1. **Resolve study.** Read `studies/<slug>/study.yaml`. If the study doesn't exist, abort: "Study '<slug>' not found. Run `/pbg-study new` to create it."

2. **Discover source docs.** Resolve `--from-plan` and each `--from-expert` path (relative to the workspace root). If neither flag is given:
   - Scan `references/expert/` for files whose filename (lowercased, without extension) contains the slug or the substring "plan".
   - Also check `workspace.yaml` under `expert_docs` for any entry whose `claims_supported` overlaps with the study's `id` or `parent_studies`.
   - If no docs are found, warn the user and offer to continue with only the study.yaml context.

3. **Read source material.** Use the Read tool on each resolved doc. If a doc is a PDF, read all pages.

4. **Draft each requested field.** For each field in `--fields`:

   - `question:` — One paragraph (at most four sentences), scientifically framed as a measurable prediction, ending with `?`. When the plan names a specific section or heading that motivates the question, cite it parenthetically (e.g., "per §3.2 of the plan"). Keep it concise.

   - `hypothesis:` — One paragraph stating the predicted outcome. Include quantitative thresholds (counts, fractions, timescales) **only when they appear explicitly in the source documents**. If the source is qualitative, write "approximately X to Y, per <citation>" rather than fabricating precision. Do not inflate specificity.

   - `objective:` — One paragraph in imperative present tense naming what the study will build, measure, or test (e.g., "Simulate … and measure … to determine …").

   - `description:` — Two to four paragraphs providing scientific context, citing source sections by their heading names. Structure: background, mechanism of interest, why this study, expected outcome.

   **v4 narrative-spine fields** (drafted only when `--include-narrative` or named explicitly in `--fields`; written YAML-direct via `pbg_superpowers.study_narrative` since these fields have no dedicated POST endpoints):

   - `report:` — Object with sub-fields. `verdict` defaults to `not-yet-run` until simulations land; `confidence` defaults to `low`; `evidence_quality` defaults to `aspirational`. Draft `objective`, `main_insight`, and `caveat` from the plan's expected-outcome + caveats sections. Leave `conclusion` blank (it's a Decide-phase field). `key_metrics` is hand-authored; do not invent numbers.

   - `study_card:` — Five one-line fields. `goal` is the one-sentence boil-down of the plan's intent. `mechanism` summarizes the biological mechanism in one paragraph. `why_before_next` explains why this study must complete before the next (read parent_studies + expert PDFs for dependencies). `expected_result` paraphrases the literature-stated success criterion. `main_expert_question` is the one question the study most wants an expert to weigh in on.

   - `biological_summary:` — Multi-paragraph plain-English mechanism narrative (the "textbook write-up"). Use 3-5 paragraphs. Markdown allowed. Distinct from `report.main_insight` (one sentence) and `study_card.mechanism` (one paragraph).

   Each draft is a plain string or YAML object suitable for direct insertion into `study.yaml`.

5. **Print preview.** Show a unified diff for each drafted field:
   - If the field currently has a user-authored value, display: `existing:` block then `proposed:` block, with a note that the default action is replace.
   - If the field is empty or missing, display `(empty) → <proposed>`.

6. **Confirm with the user.** Accept three responses:
   - `yes` — proceed to write.
   - `no` — abort without writing; print "No changes made."
   - `edit <field> <new-prompt>` — re-draft only that field using the new prompt, then repeat the preview for it before asking again. Loop until the user says `yes` or `no`.

7. **Write via API.** POST `/api/study-set-overview` with only the fields being written:

   ```json
   {"study": "<slug>", "question": "...", "hypothesis": "...", "objective": "...", "description": "..."}
   ```

   The endpoint accepts partial bodies — omit any field not being updated. After the POST, verify by fetching `/api/study/<slug>` and printing the resulting values of the written fields so the user can confirm what landed.

8. **Report.** Print a one-line summary per field: field name, character count before and after, and confirmation that the dashboard now shows the new value.

**Notes for Claude when running fill-overview:**

- Be conservative with hypothesis thresholds. Only state numbers that appear explicitly in the source docs. Prefer "approximately" phrasing over invented precision.
- A `question:` field longer than four sentences is too long — revise.
- If a field already has user-authored content that is substantively different from the draft, present both side-by-side and let the user decide before overwriting.
- `/api/study-set-overview` is the canonical endpoint. The legacy alias `/api/investigation-set-overview` exists for backwards compatibility but should not be used in new code.

#### `set-objective <study-name> '<text>'`

Replace the Study's objective. POST `/api/study-set-objective`:

```json
{"study": "<study-name>", "text": "<text>"}
```

#### `baseline-add <study-name> --name <n> --composite <id> [--params '<json>']`

Append a composite to the Study's baseline list. POST `/api/study-baseline-add`:

```json
{
  "study":     "<study-name>",
  "name":      "<unique-in-baseline>",
  "composite": "<pkg.composites.x>",
  "params":    { "k": 1, ... }
}
```

`name` must be unique within the Study's baseline. 409 on duplicate.

#### `baseline-remove <study-name> --name <n>`

Remove a baseline composite by name. POST `/api/study-baseline-remove`:

```json
{"study": "<study-name>", "name": "<baseline-entry-name>"}
```

Refuses with 409 if any variant has `base_composite` pointing to the entry (error body includes `dependents: [...]` listing the blocking variants). Refuses with 400 if removal would leave the baseline empty.

#### `variant-add <study-name> --name <n> --base-composite <baseline-name> [--params '<json>']`

Add a variant (a perturbation of a baseline composite). POST `/api/study-variant-add`:

```json
{
  "study":               "<study-name>",
  "name":                "<unique-variant-name>",
  "base_composite":      "<baseline-entry-name>",
  "parameter_overrides": { "k": 2, ... }
}
```

`base_composite` must reference an existing entry in `baseline[]`. 404 on unknown.

#### `variant-set-params <study-name> --variant <n> --params '<json>'`

Replace (not merge) a variant's parameter overrides. POST `/api/study-variant-set-params`:

```json
{"study": "<study-name>", "variant": "<n>", "parameter_overrides": {...}}
```

#### `variant-delete <study-name> --variant <n>`

Remove a variant. POST `/api/study-variant-delete`:

```json
{"study": "<study-name>", "variant": "<n>"}
```

#### `intervention-add <study-name> --name <n> [--description '<text>']`

Interventions are text-described experimental conditions. Currently text-only: no data link to variants or runs (deferred).

POST `/api/study-intervention-add`:

```json
{"study": "<study-name>", "name": "<n>", "description": "<text>"}
```

#### `intervention-update <study-name> --name <n> --description '<text>'`

POST `/api/study-intervention-update`:

```json
{"study": "<study-name>", "name": "<n>", "description": "<text>"}
```

#### `intervention-delete <study-name> --name <n>`

POST `/api/study-intervention-delete`:

```json
{"study": "<study-name>", "name": "<n>"}
```

#### `add-literature-anchor <slug> --expectation '<text>' --model-observable '<text>' [--source '<text>'] [--status '<text>'] [--cite <bib-key> ...] [--dry-run]`

Append one entry to `studies/<slug>/study.yaml.literature_anchors[]` — a literature expectation paired with the model observable that would falsify or confirm it. Lets a reviewer audit "did we implement this?" without reading code.

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`.
- `--expectation '<text>'` (required) — what the literature claims (e.g., `"DnaA-ATP / total DnaA ≈ 20-50% during steady growth"`).
- `--model-observable '<text>'` (required) — how to measure this in simulation (e.g., `"bulk[DnaA_ATP] / (bulk[DnaA_apo] + bulk[DnaA_ATP] + bulk[DnaA_ADP])"`).
- `--source '<text>'` (optional) — short citation (e.g., `"Boesen 2024 PNAS"`). Prefer `--cite` over `--source` for new entries.
- `--status '<text>'` (optional) — workspace status. Common values: `"Not yet measurable"`, `"Available via X listener"`, `"Partial"`, `"Verified — observed value matches"`. Free-form.
- `--cite <bib-key>` (optional, repeatable) — bib key from the workspace bibliography. Prefer this over `--source`.
- `--dry-run` (optional) — print the proposed diff; do not write.

YAML-direct subcommand. Shells out to `python -m pbg_superpowers.study_narrative add-literature-anchor ...` which loads the spec, appends the entry, and atomically writes.

#### `add-pivot <slug> --id <id> --question '<text>' [--alternatives 'A;B;C'] [--status <status>] [--requested-response '<text>'] [--notes '<text>'] [--dry-run]`

Append one entry to `studies/<slug>/study.yaml.design_pivot_required[]` — a named open decision point with its candidate paths. Lets an expert see what choices are blocking forward progress instead of guessing from prose.

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`.
- `--id <id>` (required) — stable slug matching `^[A-Za-z0-9][A-Za-z0-9_-]*$`, unique within this study's `design_pivot_required[]` (e.g., `dnaa-02-EQ-04`). 409-style error on duplicate.
- `--question '<text>'` (required) — the decision being made.
- `--alternatives 'A;B;C'` (optional) — semicolon-separated list of candidate paths (each typically `"A. <one-line description>"`).
- `--status <status>` (optional, default `open`) — `open | accepted | rejected | superseded-by-<slug> | obsolete | resolved`. Free-form.
- `--requested-response '<text>'` (optional) — what the author wants from a reviewer (e.g., `"Expert opinion on whether (A) or (B) is cleaner"`).
- `--notes '<text>'` (optional) — free-form notes.
- `--dry-run` (optional) — print the proposed diff; do not write.

YAML-direct subcommand.

#### `add-requirement <slug> --id <id> --title '<text>' [--kind <kind>] [--effort XS|S|M|L|XL] [--status <status>] [--description '<text>'] [--step '<text>' ...] [--unblocks 'a,b,c'] [--defer-until '<text>'] [--dry-run]`

Append one entry to `studies/<slug>/study.yaml.implementation_requirements[]` — a TODO item with status, effort, and what it unblocks. The v4-canonical place to track Build-phase work the study depends on.

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`.
- `--id <id>` (required) — slug unique within the study's `implementation_requirements[]` (e.g., `req-2-intrinsic-hydrolysis-step`). 409-style error on duplicate.
- `--title '<text>'` (required) — one-line description.
- `--kind <kind>` (optional) — common values: `listener | process | parameter_hook | data | state_variables | step`. Free-form.
- `--effort XS|S|M|L|XL` (optional) — t-shirt size. Schema enforces these values.
- `--status <status>` (optional, default `planned`) — common values: `planned | in-progress | done | done-no-op | blocked`. Free-form.
- `--description '<text>'` (optional) — extended description.
- `--step '<text>'` (optional, repeatable) — one step per `--step` flag; collected into `steps[]`.
- `--unblocks 'a,b,c'` (optional) — comma-separated list of test/study names this requirement unblocks when completed.
- `--defer-until '<text>'` (optional) — gating condition; free-form.
- `--dry-run` (optional) — print the proposed diff; do not write.

YAML-direct subcommand. Refuses with a clear error if the study's `implementation_requirements` is currently in object shape (rare; v4 expects an array).

### Design→Build gate

#### `verify <slug> [--strict] [--json] [--quiet]`

Spec-verify a study before running it. Catches the cross-reference errors that would otherwise show up only after a Simulate phase: behavior_tests referencing simulations that don't exist, variants pointing at unknown baselines, parent_studies that don't resolve, cite keys missing from the workspace bibliography, findings referencing tests that aren't declared, follow-up proposals linking findings that don't exist.

**What's checked** (workspace-agnostic):

- Every baseline has `name` + `composite`.
- Every variant references a real baseline (`base_composite` resolves).
- Every `simulation_set[].from` references a baseline or variant.
- Every `behavior_tests[].requires_simulation` references a baseline / variant / simulation_set entry.
- Every `behavior_tests[].measure.observable` references a declared `observables[]` entry (soft-skipped when `observables[]` is absent — many workspaces inline measure shapes).
- Every `parent_studies` slug resolves under the workspace.
- Every `cites` bibtex key appears in `references/references.bib` (soft-skipped when no bib file exists).
- Every `findings[].evidence.from_test` (or `from_tests[]`) resolves to a `behavior_tests[].name`.
- Every `followup_proposals[].linked_finding` resolves to a `findings[].id`.

**What's NOT checked** (requires workspace runtime; out of scope for the design→build gate):

- Whether the composite actually accepts the variant's parameter overrides (would require importing the composite — needs the workspace venv).
- Whether observable store paths actually resolve in a real simulation run (would require running the composite or reading initial_state.json — workspace-specific cache layout).

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`. Abort if `study.yaml` is missing.
- `--strict` (optional) — also fail (exit 1) on warnings. Useful in CI.
- `--json` (optional) — emit `{study_yaml, findings, summary}` JSON for tooling.
- `--quiet` (optional) — suppress output on success (still nonzero exit on failure).

**Behavior:**

1. Walk up from cwd to find `workspace.yaml`.
2. Resolve `studies/<slug>/study.yaml`. Abort if absent.
3. Shell out to the helper:
   ```bash
   python3 -m pbg_superpowers.study_verify studies/<slug>/study.yaml
   ```
4. Surface findings grouped by level (error / warning / info). Each finding includes a `check:` identifier, dotted `field_path`, and a one-line message.
5. Exit 0 if clean; exit 1 if any error (or any warning with `--strict`); exit 2 if the study.yaml file doesn't exist.

**Notes:**

- This is a thin wrapper around the Python helper — no dashboard API. The check set lives in `pbg_superpowers/study_verify.py`; tests pin each check (`tests/test_study_verify.py`).
- Run this after every Design-phase edit. The dashboard's save-time schema validator catches structural errors; `verify` catches semantic cross-reference errors that the schema can't express.

#### `preview-viz <slug> [--name <viz-name>]`

Re-render the study's declared `visualizations[]` against whatever data exists, so a misconfigured viz fails in seconds instead of after a full Simulate phase. POST `/api/study-viz-render`:

```json
{"name": "<slug>"}
```

The dashboard builds a 1-step composite for each viz entry, runs it against the workspace's `core`, and writes the rendered HTML to `studies/<slug>/viz/<viz-name>.html`. The response lists the rendered paths and surfaces per-viz render errors so you can fix them before kicking off a long run.

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`.
- `--name <viz-name>` (optional) — server-side filtering by viz name is not yet implemented; this flag is reserved for forward compatibility. Today the endpoint always re-renders all declared viz; the skill still accepts the flag and grep-filters the response client-side.

**Behavior:**

1. Walk up from cwd to find `workspace.yaml`.
2. POST `{name: <slug>}` to `/api/study-viz-render`. Surfaces a 404 if the study doesn't exist; a 500 with `error: render failed: ...` if a viz raised.
3. Print the JSON response: `{ok, study, n_visualizations, viz_paths}`. When `--name` is set, restrict the printed `viz_paths` to entries ending with `/<viz-name>.html`.

**Notes:**

- This is the build-phase counterpart of `verify`. `verify` catches static spec errors; `preview-viz` catches dynamic render errors (missing observables in the composite, wrong registry address for the Visualization class, bad config kwargs).
- Repeated invocations are idempotent — each viz HTML is overwritten in place.

### Simulate subcommands

#### `run-baseline <study-name> [--composite <name>] [--steps N] [--no-refresh-viz]`

Run a baseline composite. POST `/api/study-run-baseline`:

```json
{"study": "<study-name>", "composite": "<baseline-entry-name>", "steps": 5}
```

`composite` is the entry name in `baseline[]`. If omitted, defaults to `baseline[0]`.

After a successful run, automatically invokes `refresh-viz` for the study so registered charts regenerate against the new run. Pass `--no-refresh-viz` to skip.

#### `run-variant <study-name> --variant <n> [--steps N] [--no-refresh-viz]`

Run a variant. The server resolves the variant's `base_composite` against the Study's baseline list and layers `parameter_overrides` on top. POST `/api/study-run-variant`:

```json
{"study": "<study-name>", "variant": "<n>", "steps": 5}
```

After a successful run, automatically invokes `refresh-viz` for the study so registered charts regenerate against the new run. Pass `--no-refresh-viz` to skip.

> **Clearing stale runs between reruns.** `runs.db` accumulates a fresh
> row each invocation; the auto-renderer reads the *latest* row, so a
> failed debug run followed by a good one can produce mixed traces in
> the viz tab. Clear the per-study DB via:
>
> ```bash
> curl -X POST -H 'Content-Type: application/json' \
>   -d '{"study": "<slug>"}' \
>   "$URL/api/study-runs-clear"
> ```
>
> The endpoint truncates `runs_meta` + `history` for the named study
> and removes any `runs:` entries from `study.yaml`. Safe to call
> before re-running a problematic baseline / variant. See
> mem3dg-readdy friction log #27.

#### `run-script <study-name> [--entry <name>] [--list] [--no-refresh-viz]`

Run a study's **bespoke runner script** declared in `study.yaml.canonical_runs[]`. This is the third sibling alongside `run-baseline` / `run-variant`, and serves studies whose runners predate the dashboard's in-process composite executor — division-spanning multi-gen sims, calibration harnesses, parquet rerun wrappers (the v2ecoli `sims/run_dnaa_*.py` family is the canonical example). See `canonical_runs:` in [`docs/concepts/vivarium-dashboard-model.md`](../../docs/concepts/vivarium-dashboard-model.md#canonical-run-recipe-bespoke-scripts) for the schema.

Flow:

1. Locate `studies/<slug>/study.yaml` from the workspace root.
2. Read `canonical_runs:`. Fail with a clear message if absent or empty: *"Study <slug> has no `canonical_runs:` block. Either add one (see docs/concepts/vivarium-dashboard-model.md#canonical-run-recipe-bespoke-scripts) or use `/pbg-study run-baseline` if the study has a baseline composite."*
3. `--list`: print each entry as `<name> (default? ★) — <label or "—"> — python <script> <args...>`, exit 0.
4. Else: pick the entry whose `default: true` is set; if none flagged, pick the first. `--entry <name>` overrides.
5. Resolve `script:` against the workspace root. Fail if file doesn't exist.
6. Shell `python <script> <stringified-args...>` from the workspace root, streaming stdout/stderr through. Return the subprocess exit code.

```bash
# Run the default entry
/pbg-study run-script dnaa-01-expression-dynamics

# Pick a named entry
/pbg-study run-script dnaa-01-expression-dynamics --entry long

# Inspect what's declared without running
/pbg-study run-script dnaa-01-expression-dynamics --list
```

This is a pure shell-out — no dashboard endpoint involved. The script is expected to own its own composite construction and emitter wiring (and to call `flush_parquet(composite)` itself if it uses the parquet emitter; the context manager can't enforce flush — see v2ecoli friction note 2026-05-27 #3). Future work: a `canonical_runs:` entry could declare its emitter so a wrapper handles flush, but for now the contract is "the script does everything."

After the script exits with code 0, automatically invokes `refresh-viz` for the study so registered charts regenerate against the new run. Pass `--no-refresh-viz` to skip.

> **When NOT to use run-script.** If the study's runner can be expressed as a composite plus `parameter_overrides`, prefer `run-baseline` / `run-variant` — those go through the dashboard, surface the run in `runs.db`, and integrate with the auto-renderer. `run-script` is for runners that genuinely can't fit that mold (multi-gen division, external orchestration, custom emitter pipelines).

> **Gap — declarative sweeps not yet runnable.** The `study.yaml` schema
> (`pbg-template`, Pass B) accepts `simulation_set` entries with
> `kind: sweep`, `axes`, `seeds`, `metrics`, `candidate_selection`, and
> populated-after-execution fields (`runs[]`, `aggregate_metrics`,
> `candidates_selected`, `rejection_reasons`). No `run-sweep` subcommand
> consumes that shape today — `run-baseline` / `run-variant` only handle
> single entries. Adding a runner is tracked as Tier-B/B3 from the v2ecoli
> feedback synthesis; build it when a real workspace needs to execute a
> declared sweep.

#### `refresh-viz <study-name> [--no-auto]`

Re-render the study's `visualizations[]` charts against the **latest run** so figures never silently go stale. This is the Simulate/Evaluate companion to `preview-viz` (which checks render wiring before a run); `refresh-viz` re-stamps charts with real run output after one.

**Purpose:** resolve the latest run from the study's `runs.db`, invoke each visualization entry's declared `render:` command with the run's emitter store wired in, and stamp a `<chart>.meta.json` sidecar so freshness is auditable.

**Mechanism:**

```bash
python -c "from pathlib import Path; import yaml, json; \
  from pbg_superpowers.run_registry import latest_run; \
  from pbg_superpowers.refresh_viz import refresh_study_viz; \
  sd=Path('studies/<slug>'); spec=yaml.safe_load((sd/'study.yaml').read_text()); \
  print(json.dumps(refresh_study_viz(sd, spec, latest_run(sd/'runs.db')), indent=2))"
```

Or call the helper directly: resolve the study dir with `python -m pbg_superpowers.paths --study <slug>`; load `study.yaml`; compute `latest = pbg_superpowers.run_registry.latest_run(<study_dir>/runs.db)`; call `pbg_superpowers.refresh_viz.refresh_study_viz(<study_dir>, spec, latest)`.

**Output:** the helper returns a list of per-chart result dicts, each with `{name, chart, status}` where `status` is one of:

- `rendered` — the render command ran successfully and the chart + sidecar were restamped.
- `error` — the render command failed; the old chart is kept in place and the error is surfaced.
- `needs_manual_refresh` — the entry has no `render:` command declared, or an on-disk chart exists but isn't registered in `visualizations[]` (untracked).

**Arguments:**

- `<study-name>` (required) — study slug under `studies/<slug>/`.
- `--no-auto` (optional) — reserved; at present `refresh-viz` always runs all entries. Pass to suppress the auto-refresh that `run-baseline` / `run-variant` / `run-script` invoke after a successful run.

**Notes:**

- If `runs.db` is absent or empty (no runs yet), `refresh-viz` exits with a clear message: "No runs recorded for `<slug>` — run a baseline or variant first."
- Repeated invocations are idempotent — each chart is overwritten in place, sidecar updated.
- The `--no-auto` flag corresponds to `--no-refresh-viz` on `run-baseline` / `run-variant` / `run-script`.

#### `visualizations[].render` convention

Each entry in `study.yaml.visualizations[]` may declare a `render:` command string — a shell command executed with `cwd` set to the study directory. The placeholder `{chart}` in the command is substituted with the entry's `chart:` path (relative to the study dir). The runner exposes the latest run to the command via two environment variables:

- `PBG_RUN_DIR` — absolute path to the run's emitter store (the zarr/parquet/SQLite directory).
- `PBG_RUN_ID` — the run's UUID from `runs_meta`.

At render time a `<chart>.meta.json` sidecar is stamped alongside each chart with:

```json
{
  "source_run_id": "<uuid>",
  "generation_id": "<generation-counter>",
  "rendered_at": "<ISO-8601>",
  "command": "<the render command string, after substitution>",
  "content_hash": "<sha256 of the chart file>"
}
```

A chart is **fresh** when its `source_run_id` matches the study's latest run id; **stale** when it doesn't; **untracked** when an on-disk chart file has no corresponding `visualizations[]` entry; **unrendered** when a `visualizations[]` entry has no on-disk chart yet.

Example `visualizations[]` entry with a `render:` command:

```yaml
visualizations:
  - name: dnaa3_binding_analysis
    chart: charts/dnaa3_binding_analysis.svg
    render: "python scripts/render_dnaa3_binding_analysis.py --out {chart}"
```

When `render:` is absent the entry is still valid (the chart can be produced by other means) but `refresh-viz` will report it as `needs_manual_refresh`.

#### `clean <study-name> [--dry-run] [--include-out-paths]`

Wipe conventional simulator output for a study so a `from scratch` rerun starts clean. Closes friction note 2026-05-27 #4 ("rerun from scratch had no single command — the agent had to know all the per-study side-effects to wipe by hand").

**What gets removed** (only when actually present on disk):

- `studies/<slug>/runs.db` and its WAL/SHM siblings (`-wal`, `-shm`).
- `studies/<slug>/parquet-runs/` (the entire hive-partitioned tree).
- With `--include-out-paths`: every `args[-1]` from each `canonical_runs:` entry that ends in `.json` (the runner's `out_path` summary JSON). Off by default — those JSONs are sometimes hand-edited / version-controlled, so opt-in.

**What's never touched** (regardless of flags):

- Git-tracked files. Each candidate path is checked against `git ls-files --error-unmatch` before deletion; matches are skipped + reported as `skipped (tracked): <path>`. This prevents `clean` from blowing away an output file that's been committed.
- `studies/<slug>/study.yaml` itself.
- `studies/<slug>/sims/` (the runner scripts).
- `studies/<slug>/tests/` (the pytest suite).
- `studies/<slug>/viz/` (visualization scripts).
- `studies/<slug>/notes/` or `studies/<slug>/references/` (per CLAUDE.md cleanup-PR rule — these are field records that feed the next iteration of the spec).

**Flow:**

1. Common prelude (find `workspace.yaml`).
2. Resolve `studies/<slug>/` from the workspace root. Fail if absent.
3. Build the candidate list:
   - `runs.db`, `runs.db-wal`, `runs.db-shm` (each if exists)
   - `parquet-runs/` (if exists as dir)
   - With `--include-out-paths`: read `canonical_runs:` from `study.yaml`; for each entry, take the last positional arg from `args:`; if it ends in `.json` and resolves to a path under `studies/<slug>/`, add it.
4. For each candidate, run `git ls-files --error-unmatch <path>` (in the workspace root). On exit 0, the path is tracked — print `skipped (tracked): <path>` and skip.
5. If `--dry-run`: print each `would remove: <path>` and exit 0.
6. Otherwise remove each candidate (`rm -f` for files, `rm -rf` for `parquet-runs/`) and print `removed: <path>` per item.
7. Final summary: `cleaned <K> path(s) (S skipped, T tracked)` and the path of any next-recommended action (`/pbg-study run-baseline <slug>` or `/pbg-study run-script <slug>` depending on whether `canonical_runs:` is present).

```bash
# Preview without removing
/pbg-study clean dnaa-01-expression-dynamics --dry-run

# Wipe runtime state (runs.db + parquet-runs/)
/pbg-study clean dnaa-01-expression-dynamics

# Also wipe canonical_runs out_path JSON summaries
/pbg-study clean dnaa-01-expression-dynamics --include-out-paths
```

> **Why not a dashboard endpoint?** `clean` operates entirely on local files (no dashboard state besides `runs.db`, which the dashboard reads opportunistically). Doing this via the dashboard would mean serializing file paths over HTTP for no benefit. The skill shells `rm` directly.

> **Investigation-level fan-out.** `/pbg-investigation run` doesn't yet have a companion `clean` — call `/pbg-study clean` per-member if you want a full investigation wipe. If this becomes routine, lift a `/pbg-investigation clean <slug> [--studies a,b]` analogous to the run orchestrator.

### Evaluate subcommands

No `pbg-study` subcommands run here directly. Evaluation is driven by:

- `POST /api/study-tests-run {study}` — run the study's pytest suite (Tests tab in the dashboard); results land in `study.yaml.tests.last_results`.
- `/pbg-viz` — add or render visualizations (Visualizations tab).

### Decide subcommands

#### `set-conclusion <study-name> '<markdown>'`

Replace the Study's conclusion. POST `/api/study-set-conclusion`:

```json
{"study": "<study-name>", "text": "<markdown>"}
```

The markdown is canonically structured under H2 headers: `## Claims`, `## Evidence`, `## Limitations`, `## Next steps`.

#### `set-verdicts <slug> [--regression PASS|FAIL|MIXED|PENDING] [--basis-regression '<text>'] [--biological PASS|FAIL|MIXED|PENDING] [--basis-biological '<text>'] [--explanatory POSITIVE|NEUTRAL|NEGATIVE|PENDING] [--basis-explanatory '<text>'] [--dry-run]`

Write the v4 three-track `conclusion_verdicts` block on `studies/<slug>/study.yaml`. Distinct from `set-conclusion` (which writes the markdown conclusion blob): `set-verdicts` writes structured `{result, basis}` pairs across three orthogonal axes.

**The three tracks:**

- `regression_compatibility` — does the code still build/run cleanly? `result` is `PASS | FAIL | MIXED | PENDING`.
- `biological_validation` — does the model match the literature? `result` is `PASS | FAIL | MIXED | PENDING`.
- `explanatory_gain` — did we learn something new? `result` is `POSITIVE | NEUTRAL | NEGATIVE | PENDING`.

Lets a study be "PASS on regression but MIXED on biology" instead of being forced into one boolean. Each track's `result` and `basis` can be set independently; passing only `--biological` updates that track and leaves the others alone. Existing tracks merge — passing `--biological PASS` without `--basis-biological` keeps the previous basis text.

**Arguments:**

- `<slug>` (required) — study under `studies/<slug>/`.
- `--regression <result>` / `--basis-regression '<text>'` — update the regression track. Either flag alone is enough to update that field.
- `--biological <result>` / `--basis-biological '<text>'` — update the biological track.
- `--explanatory <result>` / `--basis-explanatory '<text>'` — update the explanatory track.
- `--dry-run` (optional) — print the proposed diff; do not write.

At least one flag is required. YAML-direct subcommand.

**Example.** Recording dnaa-02's verdicts after the simulation runs:

```bash
/pbg-study set-verdicts dnaa-02-atp-hydrolysis \
  --regression PASS --basis-regression "2026-05-17 implementation builds cleanly." \
  --biological MIXED --basis-biological "atp_fraction = 0.997, outside band [0.2, 0.5]." \
  --explanatory POSITIVE --basis-explanatory "Three findings worth keeping."
```

#### `findings <study-slug> [--auto] [--dry-run]`

Walk the study's `behavior_tests[]` outcomes (under `runs[]`) and propose
one structured finding per outcome not already covered by an entry in
`findings[]`. The Pass 10A findings protocol (see
[`vivarium-dashboard-model.md`](../../docs/concepts/vivarium-dashboard-model.md#findings-protocol-pass-10a))
formalizes each finding as `{id, kind, status, statement}` plus optional
`evidence` / `expected` / `expert_reference` / `explanation` / `next_action`
sub-objects.

**Arguments:**

- `<study-slug>` (required) — study under `studies/<slug>/`. Abort if `study.yaml` is missing.
- `--auto` (optional) — skip the interactive curation loop; write the heuristic drafts as-is. Useful for an LLM agent that has already decided what to write.
- `--dry-run` (optional) — print the proposed `findings[]` additions as a YAML diff; do not write.

**Behavior (steps Claude follows when running this subcommand):**

1. **Resolve study.** Read `studies/<slug>/study.yaml`. Abort if absent: "Study '<slug>' not found. Run `/pbg-study new` to create it."
2. **Extract outcomes.** Walk `runs[].outcomes[]` (or `runs[].test_results[]` for the flat form). For each `behavior_tests[]` outcome not already covered by a finding (match on existing `findings[].evidence.from_test`), produce a draft via the heuristic:
   - PASS → `kind: biological`, `status: confirms`, statement = "v2ecoli reproduces `<test-description>` within tolerance".
   - FAIL → ask the user: biological (`contradicts`) vs computational (`novel`). If `--auto`, default to biological/contradicts.
3. **Auto-assign `id`.** Use the next free `F-NN` (skipping any used by existing findings).
4. **Pre-fill from heuristics.** `evidence.from_run` + `evidence.from_test` + (when present) `evidence.observed`; `expected.summary` from the test's `expected_summary` or `calibration_anchor.literature_summary` when set.
5. **Surface candidate quotes.** Call `pbg_superpowers.expert_search.search_expert_docs(ws_root, terms, max_hits=3)` on a small set of keywords extracted from the test name + description. Display the top hits (doc, page, snippet) and offer them as candidate `expert_reference.quote` + `expected.cites` entries.
6. **Interactive curation (default, skipped when `--auto`).** For each draft, ask the user to fill / refine: `statement`, `expected.summary`, `expected.cites` (bib_keys), `expert_reference` (doc + quote + note), `next_action`. The user can reject the draft outright.
7. **Append to `study.yaml.findings[]`.** Atomic write: serialize updated YAML to `study.yaml.tmp`, then `os.replace()` over the original. Preserve all other top-level keys verbatim.
8. **Bibliography crosscheck (warn).** After the walk, compare every `expected.cites` entry against `references/papers.bib` keys; print a warning for any unknown bib_key so the user can decide whether to add it.
9. **Report.** Print a one-line summary: appended count, skipped (already-covered) count, unknown bib_keys count.

**Implementation note:** the bulk of the logic lives in
[`pbg_superpowers/study_findings.py`](../../pbg_superpowers/study_findings.py).
The skill shells out to it via `python -m pbg_superpowers.study_findings <slug> [--auto] [--dry-run]`,
in the same shape as the other YAML-direct subcommands (`propose-followup`, `seed-from-followup`).
The interactive step (6) is performed by the host Claude instance following the prose flow above; the Python helper handles workspace discovery, draft heuristics, expert-PDF search, atomic-write, and the bib-key crosscheck.

#### `propose-followup <parent-slug> --id <id> --title '<t>' --motivation '<m>' [--mechanism '<hyp>'] [--seed-from-file <path>] [--dry-run]`

Append one entry to `studies/<parent-slug>/study.yaml.followup_proposals[]` (creates the list if absent). This is the Decide-phase "we should also study X" capture. The proposal is later lifted into a sibling study via `seed-from-followup`.

**Arguments:**

- `<parent-slug>` (required) — existing study under `studies/<parent-slug>/`. Abort if `study.yaml` is missing.
- `--id <id>` (required) — slug matching `^[a-z0-9][a-z0-9-]*$`. Must be unique within the parent's `followup_proposals[]`. 409-style error if duplicate.
- `--title '<t>'` (required) — short human-readable title.
- `--motivation '<m>'` (required) — what gap from this study motivates the follow-up.
- `--mechanism '<hyp>'` (optional) — hypothesized missing biology/process. Stored as `hypothesized_mechanism`. Falls through to the seeded child's `model_change:` if no explicit `seed.model_change` is provided at seed time.
- `--seed-from-file <path>` (optional) — YAML file whose contents are loaded as the `seed:` block of the proposal. Free-form; common keys are `purpose`, `key_assumptions`, `model_change`, `simulation_set`, `pipeline_gate`.
- `--dry-run` (optional) — print the proposed diff and stop.

**Behavior (steps Claude follows):**

1. **Resolve study.** Read `studies/<parent-slug>/study.yaml`. If absent, abort.
2. **Check id uniqueness.** Walk `followup_proposals[]` (treat absent as empty list). If any entry has `id == --id`, abort: "Proposal '<id>' already exists on study '<parent-slug>'."
3. **Build the proposal dict.** Defaults: `status: proposed`. Include only the keys provided on the CLI; `seed:` comes from `--seed-from-file` (parsed as YAML; abort on parse error).
4. **Preview.** Print a unified diff of `followup_proposals` before/after.
5. **Confirm.** `yes` → write; `no` → abort. Skip step 6 if `--dry-run`.
6. **Atomic write.** Serialize the updated study.yaml to `studies/<parent-slug>/study.yaml.tmp`, then `mv` over the original. Preserve all other top-level keys verbatim.
7. **Report.** Print one line: `Added proposal <id> to <parent-slug>.followup_proposals (now N entries).`

#### `seed-from-followup <parent-slug> <proposal-id> [--new-slug <slug>] [--from-finding <finding-id>] [--dry-run]`

Lift a parent's `followup_proposals[id == <proposal-id>]` entry into a brand-new sibling study, stamped with `seeded_from:` and auto-linked back to the parent via `pipeline_gate.prerequisites`.

**Arguments:**

- `<parent-slug>` (required) — existing parent study.
- `<proposal-id>` (required) — id of the proposal entry to seed from. Status must be `proposed` or `accepted`; abort on `seeded` (already seeded) or `rejected`.
- `--new-slug <slug>` (optional) — slug for the new study. Default: the proposal's `id`. Abort if `studies/<new-slug>/` already exists.
- `--from-finding <finding-id>` (optional, **Pass 10B**) — id of a finding (e.g. `F-03`) on the parent's `findings[]`. When passed, pre-populates the child from that finding: `purpose:` / `key_assumptions:` from `explanation` + `next_action` + `evidence.smoking_gun`; `seeded_from.evidence` from the finding's `evidence` block; `pipeline_gate.proceed_condition` from `next_action`; `behavior_tests` carries over the parent test referenced by `evidence.from_test` (reclassified as `primary`); `model_change.notes` is stamped with a TBD pointer when `explanation` is set. The child is also stamped with `seeded_from.finding: <id>`, and the parent's proposal entry records `linked_finding: <id>` so the lineage finding → proposal → child study is queryable. Abort if the finding id isn't on the parent.
- `--dry-run` (optional) — print both proposed diffs and stop.

**Behavior (steps Claude follows):**

1. **Resolve parent.** Read `studies/<parent-slug>/study.yaml`. Find `followup_proposals[id == <proposal-id>]`. Abort if missing or if `status not in {proposed, accepted}`.
2. **Resolve new slug.** `new_slug = --new-slug or proposal.id`. Abort if `studies/<new_slug>/` exists.
3. **(Pass 10B) Resolve `--from-finding`, if passed.** Shell out to the helper:
   ```bash
   python3 -m pbg_superpowers.seed_from_followup \
     studies/<parent-slug>/study.yaml <proposal-id> <finding-id> \
     --new-slug <new_slug>
   ```
   This prints a YAML preview of (a) the child seed (`purpose` + `key_assumptions` + `seeded_from` + `pipeline_gate` + `behavior_tests` + `model_change`) and (b) the updated parent-proposal entry. If the helper exits 2, the finding id is unknown — abort with the printed error. The helper never writes; the prose flow does.
4. **Build child `study.yaml` dict** with this skeleton:
   ```yaml
   schema_version: 3
   name: <new_slug>
   phase: Design
   purpose: <proposal.seed.purpose or {question: <derived from title+motivation>, mechanism: '', expected_outcome: ''}>
   pipeline_gate:
     prerequisites: [<parent-slug>, ...any from proposal.seed.pipeline_gate.prerequisites]
     # plus enables / proceed_condition / blocks_until_resolved if present in proposal.seed.pipeline_gate
   key_assumptions: <proposal.seed.key_assumptions or []>
   model_change: <proposal.seed.model_change or proposal.hypothesized_mechanism or ''>
   simulation_set: <proposal.seed.simulation_set or []>
   seeded_from:
     study: <parent-slug>
     proposal_id: <proposal-id>
     finding: <finding-id>            # ONLY when --from-finding is passed
   ```
   The purpose-fallback question is `"<proposal.title> — <proposal.motivation>"` (single line, truncated tastefully) when `proposal.seed.purpose` is absent.

   **Pass 10B finding-to-child merge** (when `--from-finding` is passed): merge the helper's `ChildSeed` over the skeleton above with **existing keys winning** — the propose-followup seed.purpose still has priority, the finding only fills empty slots. The mapping:
   - `purpose.question` ← derived from the finding's `next_action` (e.g. "Calibrate X to match Y" → "How do we calibrate X to match Y?"). Falls back to "Investigate <statement>?" when `next_action` is absent.
   - `purpose.mechanism` ← the finding's `explanation` verbatim (when set).
   - `purpose.expected_outcome` ← the trailing clause of `next_action` if it contains target cues ("to match", "within", "in range", numeric thresholds); else empty.
   - `key_assumptions[]` ← appended with the finding's `evidence.smoking_gun` string (when present and not already in the list).
   - `seeded_from.finding` ← `<finding-id>`.
   - `seeded_from.evidence` ← a copy of the finding's `evidence` block, so the child's lineage is self-contained.
   - `pipeline_gate.proceed_condition` ← the finding's `next_action` verbatim (when set), as a starting point. Existing `proceed_condition` wins.
   - `behavior_tests[]` ← appended with the parent's behavior_test named by `evidence.from_test` (or each in `evidence.from_tests[]`), reclassified as `classification: primary` — it's the test the follow-up exists to make pass. Dedup'd by name; an existing same-named entry wins.
   - `model_change.notes` ← `"TBD — see purpose.mechanism for the hypothesized mechanism."` when the finding has an `explanation`. Skipped if the child's `model_change` is already a string (terse summary) — promote manually if you want enrichment.

5. **Build parent diff.** Flip the proposal entry: set `status: seeded` and `seeded_study: <new_slug>`. When `--from-finding` was passed AND the proposal doesn't already have a `linked_finding:` key, also set `linked_finding: <finding-id>`.
6. **Preview both diffs.** Show (a) the new `studies/<new_slug>/study.yaml` content, (b) the parent's `followup_proposals[<i>]` before/after.
7. **Confirm.** `yes` → write both; `no` → abort. Skip step 8 if `--dry-run`.
8. **Atomic writes (two).** Write the new child via tmp+rename (creating `studies/<new_slug>/` first). Write the parent via tmp+rename. If the parent write fails after the child write succeeded, `rm -rf studies/<new_slug>/` to avoid an orphaned child, then re-raise.
9. **Report.** Print: `Seeded studies/<new_slug>/study.yaml from <parent-slug>.followup_proposals[<proposal-id>]. Parent proposal marked seeded.` Append `Linked finding: <finding-id>.` when `--from-finding` was passed.

**Notes:**

- This is a YAML-direct subcommand; no dashboard API endpoint exists yet (mirrors `/pbg-investigation`'s YAML-direct write pattern).
- After seeding, the child appears in the dashboard's Studies tab on the next workspace refresh; the parent's proposal entry's `seeded_study:` makes the lineage visible in the Decide panel.

### Utility

#### `open <study-name>`

Open the Study's detail page in the user's default browser. POST `/api/open-window`:

```json
{"route": "/studies/<name>"}
```

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- Common prelude ----------------------------------------------------
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace" >&2; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "Run /pbg-server start first." >&2; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"

# Helper: build a body dict from key=value flags + post to an endpoint.
post() {
  local path="$1"; shift
  local body="$1"; shift
  curl -sf -X POST -H "Content-Type: application/json" -d "$body" "$URL$path" | python3 -m json.tool
}

sub="${1:-}"; shift || true

case "$sub" in
  new)
    # Args: <study-name> <composite-id> — emits the v4-shape study.yaml
    # with the 14-section narrative spine commented in as TODO placeholders.
    # The endpoint is /api/investigation-create (legacy route name; aliased
    # to /api/study-create in ENDPOINT_ALIASES). The body's `name` field
    # is the new study's slug; `source` is the composite ref.
    SNAME="$1"; CID="$2"
    [ -n "$SNAME" ] && [ -n "$CID" ] || { echo "Usage: /pbg-study new <study-name> <composite-id>" >&2; exit 1; }
    BODY=$(SNAME="$SNAME" CID="$CID" python3 -c "
import json, os
print(json.dumps({'name': os.environ['SNAME'], 'source': os.environ['CID']}))")
    post "/api/investigation-create" "$BODY"
    ;;

  set-objective)
    NAME="$1"; TEXT="$2"
    BODY=$(NAME="$NAME" TEXT="$TEXT" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'text': os.environ['TEXT']}))")
    post "/api/study-set-objective" "$BODY"
    ;;

  set-conclusion)
    NAME="$1"; MD="$2"
    BODY=$(NAME="$NAME" MD="$MD" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'text': os.environ['MD']}))")
    post "/api/study-set-conclusion" "$BODY"
    ;;

  fill-overview)
    # fill-overview is a Claude-driven subcommand. The shell case dispatches it,
    # but the actual work (reading docs, drafting fields, confirm loop, POST) is
    # performed by the host Claude instance following the prose steps in SKILL.md
    # rather than by this bash script.  The case arm below is a no-op placeholder
    # so the usage block does not fire; Claude handles everything in-context.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: fill-overview requires a study slug." >&2; exit 1; }
    # Claude: follow the "fill-overview" behavior steps in SKILL.md starting at
    # step 1 (Resolve study). The remaining flags (--from-plan, --from-expert,
    # --fields, --dry-run) are parsed from "$@" by Claude inline.
    ;;

  baseline-add)
    NAME="$1"; shift
    BNAME=""; COMPOSITE=""; PARAMS="{}"
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)      BNAME="$2";     shift 2 ;;
        --composite) COMPOSITE="$2"; shift 2 ;;
        --params)    PARAMS="$2";    shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$BNAME" ] && [ -n "$COMPOSITE" ] || { echo "--name and --composite required"; exit 1; }
    BODY=$(NAME="$NAME" BNAME="$BNAME" COMPOSITE="$COMPOSITE" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['BNAME'],
  'composite': os.environ['COMPOSITE'],
  'params': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-baseline-add" "$BODY"
    ;;

  baseline-remove)
    NAME="$1"; shift
    BNAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) BNAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$BNAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" BNAME="$BNAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'name': os.environ['BNAME']}))")
    post "/api/study-baseline-remove" "$BODY"
    ;;

  run-baseline)
    NAME="$1"; shift
    COMPOSITE=""; STEPS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --composite) COMPOSITE="$2"; shift 2 ;;
        --steps)     STEPS="$2";     shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    BODY=$(NAME="$NAME" COMPOSITE="$COMPOSITE" STEPS="$STEPS" python3 -c "
import json, os
b = {'study': os.environ['NAME']}
if os.environ['COMPOSITE']: b['composite'] = os.environ['COMPOSITE']
if os.environ['STEPS']: b['steps'] = int(os.environ['STEPS'])
print(json.dumps(b))")
    post "/api/study-run-baseline" "$BODY"
    ;;

  variant-add)
    NAME="$1"; shift
    VNAME=""; BASE=""; PARAMS="{}"
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)            VNAME="$2";  shift 2 ;;
        --base-composite)  BASE="$2";   shift 2 ;;
        --params)          PARAMS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] && [ -n "$BASE" ] || { echo "--name and --base-composite required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" BASE="$BASE" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['VNAME'],
  'base_composite': os.environ['BASE'],
  'parameter_overrides': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-variant-add" "$BODY"
    ;;

  variant-set-params)
    NAME="$1"; shift
    VNAME=""; PARAMS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2";  shift 2 ;;
        --params)  PARAMS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] && [ -n "$PARAMS" ] || { echo "--variant and --params required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'variant': os.environ['VNAME'],
  'parameter_overrides': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-variant-set-params" "$BODY"
    ;;

  variant-delete)
    NAME="$1"; shift
    VNAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] || { echo "--variant required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'variant': os.environ['VNAME']}))")
    post "/api/study-variant-delete" "$BODY"
    ;;

  run-variant)
    NAME="$1"; shift
    VNAME=""; STEPS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2"; shift 2 ;;
        --steps)   STEPS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] || { echo "--variant required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" STEPS="$STEPS" python3 -c "
import json, os
b = {'study': os.environ['NAME'], 'variant': os.environ['VNAME']}
if os.environ['STEPS']: b['steps'] = int(os.environ['STEPS'])
print(json.dumps(b))")
    post "/api/study-run-variant" "$BODY"
    ;;

  intervention-add)
    NAME="$1"; shift
    INAME=""; DESC=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)        INAME="$2"; shift 2 ;;
        --description) DESC="$2";  shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" DESC="$DESC" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['INAME'],
  'description': os.environ['DESC'],
}))")
    post "/api/study-intervention-add" "$BODY"
    ;;

  intervention-update)
    NAME="$1"; shift
    INAME=""; DESC=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)        INAME="$2"; shift 2 ;;
        --description) DESC="$2";  shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] && [ -n "$DESC" ] || { echo "--name and --description required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" DESC="$DESC" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['INAME'],
  'description': os.environ['DESC'],
}))")
    post "/api/study-intervention-update" "$BODY"
    ;;

  intervention-delete)
    NAME="$1"; shift
    INAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) INAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'name': os.environ['INAME']}))")
    post "/api/study-intervention-delete" "$BODY"
    ;;

  open)
    NAME="$1"
    BODY=$(NAME="$NAME" python3 -c "
import json, os
print(json.dumps({'route': f'/studies/{os.environ[\"NAME\"]}'}))")
    post "/api/open-window" "$BODY"
    ;;

  propose-followup|seed-from-followup)
    # Both subcommands are Claude-driven YAML-direct writes (no API endpoint).
    # Claude: follow the prose "Behavior" steps in SKILL.md for the relevant
    # subcommand. The case arm is a placeholder so the usage block does not fire.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: $sub requires a parent study slug." >&2; exit 1; }
    ;;

  findings)
    # Pass 10A. YAML-direct subcommand; the Python helper does workspace
    # discovery, draft heuristics, atomic write, and bib-key crosscheck.
    # Interactive curation (step 6 in SKILL.md) is performed by Claude.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: findings requires a study slug." >&2; exit 1; }
    shift
    EXTRA_FLAGS=()
    while [ $# -gt 0 ]; do
      case "$1" in
        --auto|--dry-run) EXTRA_FLAGS+=("$1"); shift ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    python3 -m pbg_superpowers.study_findings "$SLUG" --ws "$DIR" "${EXTRA_FLAGS[@]}"
    ;;

  set-verdicts|add-literature-anchor|add-pivot|add-requirement)
    # v4 narrative-spine subcommands. YAML-direct via pbg_superpowers.
    # study_narrative — the helper handles workspace discovery, schema-side
    # validation, dedup checks, and atomic write. All flags after the slug
    # are forwarded verbatim, so this dispatcher stays trivial.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: $sub requires a study slug." >&2; exit 1; }
    shift
    python3 -m pbg_superpowers.study_narrative --ws "$DIR" "$sub" "$SLUG" "$@"
    ;;

  verify)
    # Design→Build gate. Pure spec check; no API call. The Python helper
    # walks workspace.yaml + studies/<slug>/study.yaml and surfaces
    # cross-reference errors before any sim runs.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: verify requires a study slug." >&2; exit 1; }
    shift
    EXTRA_FLAGS=()
    while [ $# -gt 0 ]; do
      case "$1" in
        --strict|--json|--quiet) EXTRA_FLAGS+=("$1"); shift ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    STUDY_YAML="$DIR/studies/$SLUG/study.yaml"
    if [ ! -f "$STUDY_YAML" ]; then
      echo "ERROR: $STUDY_YAML not found." >&2
      exit 2
    fi
    python3 -m pbg_superpowers.study_verify "$STUDY_YAML" "${EXTRA_FLAGS[@]}"
    ;;

  preview-viz)
    # Build-phase render dry-run. Re-renders the study's declared
    # visualizations[] via the dashboard's /api/study-viz-render endpoint
    # so render errors (missing observables, wrong viz address, bad config)
    # surface in seconds instead of after a full Simulate.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: preview-viz requires a study slug." >&2; exit 1; }
    shift
    FILTER_NAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) FILTER_NAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    BODY=$(NAME="$SLUG" python3 -c "
import json, os
print(json.dumps({'name': os.environ['NAME']}))")
    RAW=$(curl -sf -X POST -H "Content-Type: application/json" \
      -d "$BODY" "$URL/api/study-viz-render" || true)
    if [ -z "$RAW" ]; then
      echo "ERROR: /api/study-viz-render returned no body (study missing or server error)." >&2
      exit 1
    fi
    if [ -n "$FILTER_NAME" ]; then
      RAW=$(FILTER="$FILTER_NAME" python3 -c "
import json, os, sys
data = json.load(sys.stdin)
if isinstance(data.get('viz_paths'), list):
    needle = '/' + os.environ['FILTER'] + '.html'
    data['viz_paths'] = [p for p in data['viz_paths'] if p.endswith(needle)]
    data['n_visualizations'] = len(data['viz_paths'])
print(json.dumps(data))
" <<<"$RAW")
    fi
    echo "$RAW" | python3 -m json.tool
    ;;

  *)
    cat <<EOF
Usage:
  /pbg-study new <study-name> <composite-id>
  /pbg-study fill-overview <slug> [--from-plan <path>] [--from-expert <path>...] [--fields <comma-list>] [--dry-run]
  /pbg-study set-objective <study-name> '<text>'
  /pbg-study set-conclusion <study-name> '<markdown>'

  /pbg-study baseline-add    <study-name> --name <n> --composite <id> [--params '<json>']
  /pbg-study baseline-remove <study-name> --name <n>
  /pbg-study run-baseline    <study-name> [--composite <n>] [--steps N]

  /pbg-study variant-add        <study-name> --name <n> --base-composite <baseline-name> [--params '<json>']
  /pbg-study variant-set-params <study-name> --variant <n> --params '<json>'
  /pbg-study variant-delete     <study-name> --variant <n>
  /pbg-study run-variant        <study-name> --variant <n> [--steps N]

  /pbg-study intervention-add    <study-name> --name <n> [--description '<text>']
  /pbg-study intervention-update <study-name> --name <n> --description '<text>'
  /pbg-study intervention-delete <study-name> --name <n>

  /pbg-study verify              <study-slug> [--strict] [--json] [--quiet]
  /pbg-study preview-viz         <study-slug> [--name <viz-name>]
  /pbg-study refresh-viz         <study-slug> [--no-auto]

  /pbg-study findings            <study-slug> [--auto] [--dry-run]

  /pbg-study set-verdicts            <study-slug> [--regression PASS|FAIL|MIXED|PENDING] [--basis-regression '<t>'] [--biological ...] [--basis-biological '<t>'] [--explanatory POSITIVE|NEUTRAL|NEGATIVE|PENDING] [--basis-explanatory '<t>'] [--dry-run]
  /pbg-study add-literature-anchor   <study-slug> --expectation '<t>' --model-observable '<t>' [--source '<t>'] [--status '<t>'] [--cite <bib-key> ...] [--dry-run]
  /pbg-study add-pivot               <study-slug> --id <id> --question '<t>' [--alternatives 'A;B;C'] [--status <s>] [--requested-response '<t>'] [--notes '<t>'] [--dry-run]
  /pbg-study add-requirement         <study-slug> --id <id> --title '<t>' [--kind <k>] [--effort XS|S|M|L|XL] [--status <s>] [--description '<t>'] [--step '<t>' ...] [--unblocks 'a,b,c'] [--defer-until '<t>'] [--dry-run]

  /pbg-study propose-followup    <parent-slug> --id <id> --title '<t>' --motivation '<m>' [--mechanism '<hyp>'] [--seed-from-file <path>] [--dry-run]
  /pbg-study seed-from-followup  <parent-slug> <proposal-id> [--new-slug <slug>] [--from-finding <id>] [--dry-run]

  /pbg-study open <study-name>
EOF
    exit 1
    ;;
esac
```

## Examples

```text
# Create a study from a composite (emits a v4-shape study.yaml with the
# 14-section narrative spine commented in as TODO placeholders)
/pbg-study new dnaa-binding pbg_chromosome_rep1.composites.dnaa-binding

# Draft question, hypothesis, objective, description from plan + expert PDFs
/pbg-study fill-overview dnaa-01 --from-plan references/expert/dnaa-plan.pdf
# Restrict to just question and hypothesis, dry-run first
/pbg-study fill-overview dnaa-01 --fields question,hypothesis --dry-run
# Provide extra expert doc
/pbg-study fill-overview dnaa-01 --from-plan references/expert/dnaa-plan.pdf --from-expert references/expert/grimwade2007.pdf

# Set the objective
/pbg-study set-objective dnaa-binding "Does DnaA threshold gate initiation?"

# Add a second baseline composite to compare
/pbg-study baseline-add dnaa-binding --name alt --composite pbg_chromosome_rep1.composites.alt-binding

# Add a low-threshold variant of the original baseline
/pbg-study variant-add dnaa-binding --name low --base-composite dnaa-binding --params '{"threshold": 30}'

# Run the variant
/pbg-study run-variant dnaa-binding --variant low

# Record a textual intervention
/pbg-study intervention-add dnaa-binding --name heat-shock --description "+10C for 5 min at t=10"

# Write conclusions
/pbg-study set-conclusion dnaa-binding "## Claims
- Threshold of 50 fits best
## Evidence
- See runs 3-7
## Limitations
- Single-cell only
## Next steps
- Multi-cell run"

# Verify the spec before kicking off a Simulate phase
/pbg-study verify dnaa-01-expression-dynamics
# CI-style: fail on warnings too
/pbg-study verify dnaa-01-expression-dynamics --strict
# Tooling-style: emit JSON for a wrapper script
/pbg-study verify dnaa-01-expression-dynamics --json

# Render declared viz against any existing data to catch config errors fast
/pbg-study preview-viz dnaa-01-expression-dynamics
# Filter to a single viz (server-side filter not yet implemented; client-side filter)
/pbg-study preview-viz dnaa-01-expression-dynamics --name autorepression-pearson

# Walk a study's behavior_test outcomes and propose structured findings
/pbg-study findings dnaa-01-expression-dynamics
# Skip interactive prompts; write heuristic drafts as-is
/pbg-study findings dnaa-01-expression-dynamics --auto
# Dry-run: print the proposed YAML diff, don't write
/pbg-study findings dnaa-01-expression-dynamics --dry-run

# Propose a Decide-phase follow-up study
/pbg-study propose-followup dnaa-binding \
  --id replisome-coupling \
  --title "Couple DnaA threshold to replisome assembly" \
  --motivation "Current study treats threshold-crossing as instantaneous initiation; downstream replisome dynamics are not modeled." \
  --mechanism "Add a replisome-loading Process gated by the DnaA-ATP fraction; transition from initiation event to fork-progression rate."

# Same, but with a richer seed block pre-authored as YAML
/pbg-study propose-followup dnaa-binding \
  --id replisome-coupling \
  --title "Couple DnaA threshold to replisome assembly" \
  --motivation "..." \
  --seed-from-file references/proposals/replisome-coupling.seed.yaml

# Seed a new study from that proposal (default slug = proposal id)
/pbg-study seed-from-followup dnaa-binding replisome-coupling
# Override the child slug
/pbg-study seed-from-followup dnaa-binding replisome-coupling --new-slug dnaa-03-replisome-coupling
# Pass 10B: seed from a specific finding on the parent (pre-populates purpose +
# key_assumptions from the finding's next_action / explanation / smoking_gun,
# and stamps seeded_from.finding on the child + linked_finding on the proposal)
/pbg-study seed-from-followup dnaa-01 calibrate-dars --from-finding F-03 --new-slug dnaa-02-dars-calibration

# Open in browser
/pbg-study open dnaa-binding
```

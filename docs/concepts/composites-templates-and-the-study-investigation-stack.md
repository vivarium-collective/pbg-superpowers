# Composites, Templates, and the Study/Investigation Stack

How the vivarium-workbench data model layers research metadata — a question, its
evidence, and the argument several results build together — over a single runnable
substrate: the **process-bigraph composite**. And how a *composite template* — a
document with open **sites** (holes) — is the shape studies and investigations are
actually built from.

> Companion to [`vivarium-workbench-model.md`](vivarium-workbench-model.md), which
> is the source of truth for the on-disk YAML shapes and the dashboard API surface.
> This document is the conceptual bridge from those shapes *down* to the
> process-bigraph substrate. The template/site formalism lives in
> [`process_bigraph/templates.py`] and bigraph-schema's Milner implementation
> (`bigraph_schema/assembly.py`, `bigraph_schema/schema.py` `Site`); see
> bigraph-schema `.claude/plans/milner-formalism.md`.

---

## 1. The big idea

Three layers of metadata sit over one runnable object. Read the stack top-down and
it's an argument; read it bottom-up and it's a simulation.

```
Workspace  (workspace.yaml + viva_<pkg>/ + .pbg/ runtime state)
│
├─ Investigation   investigations/<slug>/investigation.yaml   (schema v2, 9-section spine)
│    = a named collection of studies under one research question
│    = also a git BRANCH and a WORKTREE (1:1:1)
│    └─ studies: [<slug>, …]   +   DAG computed from each study's prerequisites
│
├─ Study   studies/<slug>/study.yaml   (schema v3/v4, 8-section + v4 narrative spine)
│    = one research question wrapped around one-or-more composites
│    └─ baseline: [{name, composite: <pkg.composites.x>, params}]   ← points DOWN
│
└─ Composite   viva_<pkg>/composites/<id>.composite.json (or a generator .py)
     = the actual process-bigraph document — the only runnable thing
```

**The one sentence to remember:** a **Composite** is the runnable object; a **Study**
is the reason you run it; an **Investigation** is the argument several studies build
together. Everything above the composite is metadata that *references* composites by a
dotted id and records what came out — with one important twist covered in §4: an
investigation is itself *compiled into* a composite.

Why the split earns its keep: the composite is reusable across many questions; the
study attaches *one* question, one emit-contract, and one pass/fail bar to it; the
investigation lets a dozen such questions accumulate into a defensible claim. You can
re-run the science without rewriting the argument, and audit the argument without
re-reading the code.

---

## 2. The composite

A composite is a **process-bigraph document**: one `state` map whose entries are
**typed nodes**. There are two kinds of node, and a composite is nothing but these two
kinds wired together.

- **Processes** — the moving parts. A node with `_type: process` names an `address`
  (which Process class), a `config`, an `interval`/schedule, and an `update` that
  advances state each step. This is where the simulator actually computes.
- **Stores** — the state. A store holds typed values (a concentration field, a
  molecule count, the clock). Processes never talk to each other directly; they read
  and write **shared stores**, and that wiring *is* the coupling.

### Anatomy

Each process node's `inputs`/`outputs` are **paths into shared stores**. Change a path
and you rewire the model; two processes that name the same store path are now coupled.
Nothing else connects them. This is a real node from
`spatio_flux/composites/fig07-1-community-dfba.composite.json`:

```jsonc
"ecoli core dFBA": {
  "_type":    "process",
  "address":  "local:DynamicFBA",           // which Process class, resolved in the registry
  "config":   { "model_file": "textbook", "kinetic_params": { /* … */ } },
  "inputs":   { "substrates": { "glucose": ["fields", "glucose"] },   // ← wiring path
                "biomass": ["fields", "ecoli core"] },                //   into a shared store
  "outputs":  { "substrates": { "glucose": ["fields", "glucose"] }, /* … */ },
  "interval": 1.0
}
```

An **address** is `protocol:path`. `local:` means "resolve this name in the local
registry (`core.link_registry`), which `allocate_core()`/`build_core()` populated by
walking the installed packages"; `DynamicFBA` is the registered Process class name.

Two more structural facts: a composite can **nest** — a node can itself be a
sub-composite, so big models are built from small ones (containment) — and time is
**per-process** (`interval`), so fast and slow processes advance on one shared state.

### Processes and draft processes

A **Process** is a Python class with typed `inputs()`/`outputs()` and an `update()`;
wrapping a simulator (via `/viva-expert`) means writing one. But you don't always have
the mechanism yet — and that's what a **draft process** is for.

A `DraftProcess` (a process-bigraph **core** primitive, ≥ 1.8.3 —
`from process_bigraph import DraftProcess, draft_process`) declares a **contract**:
input/output ports plus a human-readable description of the transformation it is *meant*
to perform — but carries **no `update` dynamics**. It inherits the base no-op update, so
if stepped it stays inert and never fabricates behavior. That lets you drop a node into
the model's topology, wire it to stores, and review the whole thing *before* committing
the biology.

```python
from process_bigraph import DraftProcess, draft_process

@draft_process(name="PTH secretion",
    inputs={"ca_sense": "float"}, outputs={"pth_out": "float"},
    contract={"summary": "...", "senses": "...", "makes": "..."})
class PTHSecretion(DraftProcess):
    pass
```

Because a workspace's `build_core()` walks the package and registers every Process, a
module-scope draft **auto-appears in the dashboard** under Modules → Processes, marked
DRAFT, with its ports and contract — no workbench change required.

---

## 3. Templates: composite documents with holes (sites)

Every composite above is **ground**: every node concrete, ready to run. A **template**
is a composite document that is *not* ground — it has open **sites**.

A site is a **place-graph hole**, written `{"_type": "site", "_sort": <face>}`: a slot
where a whole composite, process, or value plugs in. This is Milner's bigraph site
(Def. 2.1), implemented in bigraph-schema — a document with sites describes a *context*,
not a runnable state tree, and `Composite` **refuses to run one** until every required
site is filled ("an open site is a hole where a process should be", `composite.py`).

Here is a real **study template** (from `process-bigraph/tests.py`) — the
analysis/emitter/report-card network is fixed, and the model is left as a hole:

```jsonc
// a STUDY TEMPLATE — analysis/emitter network fixed, the model is a hole
{ "study": {
    "threshold": { "_type": "site", "_sort": "float" },          // a VALUE hole
    "sim": { "_type": "step", "address": "local:SimulationStep",
      "config": { "state": {
        "model":   { "_type": "site", "_sort": MODEL_FACE },     // ← plug a COMPOSITE in here
        "emitter": { "address": { "_type": "site", "_sort": "emitter" }, /* … */ } } } },
    "report_cards": {
      "card": { "_type": "site", "_sort": CARD_FACE } } } }      // plug a REPORT CARD in here

open_sites(template) → [ study/threshold,
                         study/sim/config/state/model,           // the model hole
                         study/sim/config/state/emitter/address,
                         study/report_cards/card ]
```

The `_sort` **types the hole** — what may plug in (a model composite, an emitter, a
card, a bare `float`). Filling is `fill_sites(core, template, bindings)`: plug a filler
into a site by path and the hole is gone — "once a site is filled there is no site
anymore." Fill every required site → the document is **ground** → it runs. A site
carrying a `_default` is optional; one without is required.

| Template kind | Shape | Fill / build helper |
|---|---|---|
| **Study template** | analysis/emitter/card network fixed; **the model is a site** | `template_document(core, tmpl, bindings)` — fills + renders, raises naming any required hole left empty |
| **Investigation template** | **one site per member study** | `investigation_document(core, tmpl, bindings)` — fills a member's site to admit it, **prunes** members left open |

Investigation gating is expressed as *filling*, not scheduling: an unfilled member site
is dropped from the built document (`prune_open_regions`), so a blocked prerequisite
simply never appears in the run — the engine never has to decide "don't run this."

### Three things that all look like "blanks" — keep them apart

- **A site** (`_type: site`) is an *empty structural hole* — no node there yet; you plug
  a whole composite/process/value in. **This is the template mechanism.**
- **A draft process** is a node that *is* there but inert (ports + contract, no
  `update`) — a placeholder *node*, not a hole.
- **`config` / `params` / `${name}` substitution** fills a node's *parameters* — rate
  constants, a model file — not a hole and not a node. (`${name}` placeholders live in
  `composite_spec.py`; `params`/`parameter_overrides` are merged at build.)

So a template is specialized two ways: **fill its sites** (structure) and **set its
parameters** (values). A study picks a composite for the model site and sets its params;
an investigation fills one site per member study.

### Static vs generator composites

A ground composite comes in two forms: a **static** inline `state` (the
`.composite.json` above) or a **generator** — a `@composite_generator` /
`CompositeSpec` function that *builds* the state (e.g. from a ParCa cache),
parameterized by its arguments. The generator is the parameter-driven cousin of a
template; sites are the structural mechanism.

---

## 4. How studies and investigations use it

### A study specializes the template

A study doesn't rebuild the composite — it wraps one question, one specialization, and
one pass/fail bar around it. Five fields do the joining (full field docs in
[`vivarium-workbench-model.md`](vivarium-workbench-model.md)):

| Field | Role in the join |
|---|---|
| `baseline[]` / `conditions.baseline` | **Which** composite(s) to run — a list, so one study can compare several. |
| `variants[]` | A baseline + `parameter_overrides` — the parameter fill-in surface, no structural edits. |
| `simulation_set[]` | The run recipe: `base_model`, `perturbation`, `condition`, `seeds`, `duration`. |
| `readouts[].store_path` | The **emit contract** — ties a named observable to the exact store path in the composite's output tree. |
| `behavior_tests[]` | `measure` + `pass_if` over those readouts — the verdict. |

At run time `POST /api/study-run-baseline` resolves the `baseline` id, **builds that
composite in-process**, merges the study's `params`, runs it, and records the trajectory
in `runs.db`. The study itself is never compiled into a composite — it stays metadata
that *points at* one and reads back what came out. (Per-test pass/fail pills are
**derived on read** from the latest run's `outcomes[test].result`, never from a
hand-set `status:`.)

### An investigation is compiled into a composite

An investigation groups member studies into one argument — and, since August 2026, is
itself **compiled into a process-bigraph composite** (the investigation template made
concrete).

The investigation-as-composite work (vivarium-workbench **PR #715, merged 2026-08-03,
on `main`**) provides `build_investigation_composite` / `run_investigation_composite`, a
`rebuild_investigation_composite` mutation behind
`POST /api/investigation-composite-rebuild`, and a `run_investigation` CLI runner. It
models the investigation itself as a Composite: each Study becomes a `StudyStep` node,
and each `pipeline_gate.prerequisites` edge becomes **store wiring**, so the real
process-bigraph scheduler orders execution.

This is the **investigation template** of §3 made concrete:
`process_bigraph/templates.py` builds an investigation document with **one site per
member study**; `investigation_document` fills a member's site to admit it and prunes
the ones left open. Recursion in one line: an investigation is a composite whose nodes
are `StudyStep`s, and each `StudyStep` in turn builds its own study's composite.

The older orchestrator path — walk `studies:` and shell each member's `canonical_runs:`
script — still exists for bespoke runners.

**The dependency DAG.** `studies: []` controls grouping/visibility and run order; the
DAG is computed at render time from each member's `pipeline_gate.prerequisites`, with
edge semantics `leads-to · supports · regulatory · refutes`. In the compiled form,
those same prerequisite edges *are* the store wiring that sequences execution.
**Investigation ≡ branch ≡ worktree**, so parallel agents each drive one without
colliding on runtime DBs or dashboard ports.

### What compiles, what stays a reference

| Layer | How it becomes runnable | Compiled to a composite? |
|---|---|---|
| Composite | It *is* the process-bigraph document (or a generator that emits one) | — (it is the target) |
| Study | Resolves its `baseline` id → builds that composite in-process, applies `params` | **No** — reference + param merge |
| Investigation | Compiled to a Composite of `StudyStep`s wired by prerequisites (legacy orchestrator still available) | **Yes** — PR #715, on `main` |

---

## 5. Worked example — `spatio-flux`, end to end

`spatio-flux` builds the Process-Bigraph paper's figures: one investigation, one study
per figure. Following Figure 7:

**① Investigation** — `investigations/paper-figures/investigation.yaml`:

```yaml
schema_version: 2
name: paper-figures
title: Process Bigraph paper — figures
studies: [fig-01, fig-02, fig-03, fig-07, fig-08]
```

Five member studies, no explicit prerequisites → a flat DAG.

**② Study** — `studies/fig-07/study.yaml` frames one figure over **three** composites:

```yaml
schema_version: 3
name: fig-07
investigation: paper-figures
status: complete
confidence: Accepted
baseline:
  - {name: 7-1-community-dfba,     composite: spatio_flux.composites.fig07-1-community-dfba}
  - {name: 7-2-comets,            composite: spatio_flux.composites.fig07-2-comets}
  - {name: 7-3-brownian-particles, composite: spatio_flux.composites.fig07-3-brownian-particles}
behavior_tests: [bigraph-loom image generated correctly]
runs:
  - {name: '…fig07-1-community-dfba__1786323957__36c785', status: completed}
```

`baseline[]` holds all three panels; `simulation_set` are the recipes, `runs[]` the
executions, `visualizations[]` the outputs, `behavior_tests` the gate.

**③ Composite** — `spatio_flux.composites.fig07-1-community-dfba` resolves to the
process-bigraph document the engine runs: a community of `local:DynamicFBA` processes
(one per species) plus `local:MonodKinetics`, all wired through one shared `fields`
store. Coupling happens *only* through those input/output paths. `fig-07`'s
`readouts[].store_path` point at paths like `fields/glucose`; its `behavior_tests`
measure over them; its `runs` land in `runs.db`; and `paper-figures` groups `fig-07`
with its four sibling figure-studies.

The whole chain, in one line: **shared-store composite → study that questions, runs,
and tests it → investigation that collects the figures into a single paper-shaped
claim.**

---

## 6. Where the code lives

Four repos, stacked by dependency: **bigraph-schema** (types) ⊂ **process-bigraph**
(engine + composite/template primitives) ⊂ **vivarium-workbench** (server +
investigation-as-composite) ⊂ **viva-superpowers** (`/viva-*` skills + authoring). Each
lower layer is imported by the ones above it.

### bigraph-schema — the type system beneath every store

| File | What it is |
|---|---|
| `bigraph_schema/core.py` | The `TypeSystem` — types, ports, schema resolution. |
| `bigraph_schema/schema.py` · `parse.py` | Schema definitions + the type-grammar parser; the `Site` type. |
| `bigraph_schema/assembly.py` | The Milner bigraph algebra — `interfaces`, `compose`, `tensor`, `fill_sites`. |
| `bigraph_schema/methods/apply.py` | The store-write law — how a typed update is applied to state. |
| `bigraph_schema/methods/transform.py` · `generalize.py` · `merge.py` · `resolve.py` | Schema→schema transforms + type ops. |

### process-bigraph — the engine + composite / process / template primitives

| File | What it is |
|---|---|
| `process_bigraph/composite.py` | The `Composite` class + `allocate_core()` (the registry); ground-check of sites. |
| `process_bigraph/templates.py` | Study/investigation **templates** — `open_sites`, `fill_template`, `template_document`, `investigation_document`, `prune_open_regions`. |
| `process_bigraph/composite_spec.py` | `CompositeSpec` — the unified static/generator front-end; `${name}` placeholders. |
| `process_bigraph/composite_generator.py` | The `@composite_generator` decorator (parameterized composites). |
| `process_bigraph/draft_process.py` | `DraftProcess` + `@draft_process` — contract, no dynamics. |
| `process_bigraph/composite_discovery.py` · `scheduling.py` · `emitter.py` | Package discovery/registration; per-process interval scheduler; emitters. |

### vivarium-workbench — the dashboard server + investigation-as-composite

| File | What it is |
|---|---|
| `vivarium_workbench/api/app.py` | The HTTP API — `/api/study-*`, `/api/iset/*`, `/api/investigation-composite-rebuild`. |
| `lib/investigation_steps.py` | `StudyStep` + `InvestigationAnalysisStep` (studies as nodes). |
| `lib/investigation_execution.py` | `build_investigation_composite` / `run_investigation_composite`. |
| `lib/composite_mutations.py` | `rebuild_investigation_composite` + composite edits. |
| `lib/study_runs.py` · `cli_runs.py` | Run baseline / variant / investigation. |
| `env_worker.py` | The spawned worker — `run_study` / `run_investigation_analysis` capabilities. |
| `templates/study-detail.html` · `loom/` | The 5-act study-spine UI; the composite-explorer (loom) view. |

### viva-superpowers — the `/viva-*` skills + study/investigation authoring

| File | What it is |
|---|---|
| `docs/concepts/vivarium-workbench-model.md` | The data-model source of truth (on-disk YAML + API). |
| `skills/` | The `/viva-*` skills — study, investigation, expert, viz, run. |
| `viva_superpowers/scaffold.py` | Emits the study/investigation YAML spines (TODO placeholders). |
| `viva_superpowers/study_canonicalize.py` · `investigation_canonicalize.py` | Canonicalize specs on read. |
| `viva_superpowers/study_status.py` | `study_clarity_summary` — the derive-on-read status source. |
| `viva_superpowers/report.py` · `report_linter.py` · `test_audit.py` · `rigor.py` | Report render + lint + assurance/rigor scorecards. |

---

## 7. Study lifecycle & on-disk layout

A study moves through five phases, each writing to a different part of the spine:

| Phase | Produces | Writes to |
|---|---|---|
| **Design** | The spec: question, gate, run set, tests | `purpose`, `pipeline_gate`, `simulation_set`, `behavior_tests` |
| **Build** | Executable code: Process classes + composites | `model_change`, `implementation_requirements`, the composite files |
| **Simulate** | The runs: trajectories | `runs.db` |
| **Evaluate** | The verdict: test results + figures | `outcomes`, `visualizations`, `findings` |
| **Decide** | Conclusion + follow-ups | `conclusion_verdicts`, `discovery_implications` |

Coarsely sequential, iterative in practice: Evaluate routinely sends you back to Build.
An investigation card surfaces its *slowest-phase* member.

```
# A workspace root
workspace.yaml
viva_<pkg>/composites/<id>.composite.json    # the runnable substrate (ground or a template)
investigations/<slug>/investigation.yaml      # the collection (= branch = worktree)
studies/<slug>/study.yaml                     # the question + spine
studies/<slug>/runs.db                        # canonical run + outcome record
studies/<slug>/parquet-runs/<run>/            # emitted trajectories
.pbg/server/                                  # dashboard runtime state
```

To see it rendered: `/viva-workbench start`, then open an investigation — the same three
layers appear as the **Investigation graph** (nodes = studies, Asks → Finds →
Confidence), the **study-detail spine** (Design / Evidence / Assurance / Decision acts),
and the **Composite Explorer** (the wired process graph).

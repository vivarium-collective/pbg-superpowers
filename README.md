# pbg-superpowers

> **Canonical terminology** — see [`docs/concepts/process-bigraph-glossary.md`](docs/concepts/process-bigraph-glossary.md), anchored on Agmon & Spangler (2026).

A Claude Code plugin for building **multiscale models in the Process Bigraph framework**. `pbg-superpowers` is a library of AI-agent skills that scaffold the parts of a compositional modeling project that are mechanical but error-prone: wrapping a numerical method (or any other mechanism) as a typed Process, composing several Processes into a Composite, organizing the work into a reproducible research workspace, and managing studies + runs + visualizations through an interactive dashboard.

It is intended for **computational biologists** who want their models to be reusable, recombinable, and runnable by others — without writing the registry, packaging, schema, and report boilerplate by hand.

> **🚧 In development.** The plugin and the [vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard) it drives are under active iteration; minor versions may reshape concepts or APIs.

## Why process bigraphs?

A model in this framework is a typed graph of **Processes** (mechanisms that read and update **stores** through typed **ports**) organized hierarchically in a **place graph** (compartments inside compartments inside …). Each Process is a clean, swappable function with a typed interface; the **Composite** that wires them together is itself a Process, so models compose recursively. Orchestration — multi-timestepping, DAG-of-Steps workflows, structural rewrites — lives in the framework, not in the model.

This buys three things that matter for a compositional model: (i) **substitutability** — a Process can be replaced by any other Process exposing the same typed interface; (ii) **scale-spanning** — molecules / cells / tissues sit at different levels of the same place graph; (iii) **language-agnostic specification** — models are JSON-serializable schemas + state, not Python objects, so they can be stored, exchanged, and executed across environments.

The formal semantics are in [Agmon & Spangler (2026), Supplement 1](docs/references/papers/agmon-spangler-2026-process-bigraphs-supplement1.pdf); the framing and motivation are in the [main paper](docs/references/papers/agmon-spangler-2026-process-bigraphs-main.pdf).

## What pbg-superpowers does

For each step of building a process-bigraph project, there is a skill:

- **Wrap** an existing numerical method (ODE solver, FBA model, stochastic simulator, agent-based simulator, machine-learning surrogate, …) as a typed `Process` with declared input/output ports — either as a standalone `pbg-<tool>` repository or in-workspace.
- **Compose** several Processes into a `Composite` with a typed interface — same two paths (standalone repo or in-workspace).
- **Scaffold** a research workspace with the conventions the dashboard expects (state directories, references library, decisions log, lint, CI).
- **Manage studies** — declare baseline composites, variants (parameter perturbations or process swaps), interventions, runs, behavioral expectations, and conclusions.
- **Generate visualizations** from a natural-language description, attached to a Study.
- **Track everything in git** — every dashboard mutation commits to the active workstream branch; one PR per workstream.

The dashboard is the canonical UI for routine state changes; the skills are the alternative for code-writing tasks that benefit from Claude.

## Companion repo

This plugin orchestrates **[vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard)** — a local web UI for browsing composites, running studies, and rendering visualizations. The skills read from the dashboard's HTTP API and write to it. The canonical data model (Workspace · Study · Baseline · Variant · Intervention · Run · Visualization) is documented in [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md). New agents should read [`CLAUDE.md`](CLAUDE.md) first.

## Install

Installing has **two parts** — the Claude Code plugin (the `/pbg-*` skills) and the `pbg-superpowers` Python package the skills call into. You need both.

**1. The plugin.** Add this repo as a marketplace, then install:

    /plugin marketplace add vivarium-collective/pbg-superpowers
    /plugin install pbg-superpowers
    /reload-plugins

For local development, skip the marketplace and load the working tree directly:

    claude --plugin-dir /path/to/pbg-superpowers

**2. The Python package.** The skills shell out to `pbg_superpowers` — install it into the Python environment Claude Code runs commands in:

    pip install pbg-superpowers          # from PyPI
    pip install -e /path/to/pbg-superpowers   # editable, for development

Verify with `/help` — the `/pbg-*` skills should be listed.

## Quick start

    /pbg-workspace my-project --upstream <owner/repo>   # scaffold a workspace as a branch of an upstream model repo
    cd my-project
    /pbg-server start                                   # start the dashboard
    /pbg-list                                           # browse the workspace catalog
    /pbg-study new <package.composites.my-composite>    # create a Study from a composite
    /pbg-study run-baseline my-composite                # run it

Or — to add or wrap a new mechanism first:

    /pbg-expert <tool>                  # wrap a simulator as a standalone pbg-<tool>/ repo (with tests, report, PR)
    /pbg-wrapper <tool>                 # ...or wrap it lightly inside the current workspace
    /pbg-expert <name> <tool> <tool>    # compose two or more wrapped simulators into a sibling composite repo
    /pbg-composer <name> <tool> <tool>  # ...or compose lightly inside the current workspace

## Skills

17 skills, grouped by purpose. See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md#skill--concept-map) for the full read/write surface.

### Wrap & compose

| Skill | What it does |
|---|---|
| `/pbg-expert <tool>` | Wrap a simulator as a Process — full sibling `pbg-<tool>/` repo with Process class, tests, README, HTML report, and an open PR. The canonical wrap. |
| `/pbg-expert <name> <tools…>` | Compose two or more wrapped simulators into a sibling `pbg-<name>-composite/` repo with HTML report and PR. |
| `/pbg-wrapper <tool>` | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test stub. No sibling repo, no report. |
| `/pbg-composer <name> <tools…>` | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test stub. |
| `/pbg-suggest <request-id>` | Draft a repo name, PR title, or PR body in response to a dashboard Suggest request. |

### Workspace lifecycle & dashboard

| Skill | What it does |
|---|---|
| `/pbg-workspace <name>` | Scaffold a fresh workspace — three modes: upstream-branch (clone an upstream model repo and create a workspace branch), standalone (clone `pbg-template`), or in-place (promote an existing checkout). |
| `/pbg-server [start\|stop\|status]` | Start/stop the dashboard server in the current workspace. Required precondition for the Studies skills. |
| `/pbg-status` | Print workspace health: is this a workspace? server up? recent activity? |

### Catalog & registry

| Skill | What it does |
|---|---|
| `/pbg-install <pkg>` | Add a curated `pbg-*` package, install it, and refresh the workspace catalog. |
| `/pbg-uninstall <pkg>` | Remove an installed `pbg-*` package. |
| `/pbg-list` | Browse the workspace catalog — composites, studies, registry. |
| `/pbg-package <repo>` | Audit an external `pbg-*` repo for discovery- and packaging-convention compliance. |

### Run, explore, study

| Skill | What it does |
|---|---|
| `/pbg-run <composite-id> [--steps N]` | Run a composite directly (no Study attached). |
| `/pbg-explore <spec-id>` | Open the dashboard's Composite Explorer focused on one composite. |
| `/pbg-study <subcmd> …` | Full CRUD for **Studies** — baseline composites, variants, interventions, runs, behavioral expectations. See the [skill doc](skills/pbg-study/SKILL.md) or the [concept map](docs/concepts/vivarium-dashboard-model.md#the-concepts). |
| `/pbg-viz <study> <viz-name> '<description>'` | Generate a `Visualization` subclass from a natural-language description and attach it to a Study. |
| `/pbg-report [model\|--all]` | Regenerate `reports/index.html` after manual state changes. |

## Concepts

- **Workspace IS the model.** A workspace root contains the model's Python package (`pbg_<slug>/`), tests, references, decisions log, datasets, and a `workspace.yaml`. The workspace is the unit of reproducibility.
- **5-tab dashboard.** `Workspace inputs · Registry · Studies · Visualizations · Build Model`. Canonical UI for routine state changes; skills are the alternative for code-writing tasks. The server is opt-in — every skill works without it (Studies skills require it).
- **Studies have lists.** A Study's *baseline* is a **list** of composites; each *variant* references one of them via `base_composite` + carries flat `parameter_overrides`; *interventions* are text-only experimental conditions; *expected_behavior* entries are structured assertions (English + machine-checkable triple). See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md) for the canonical data model and [`docs/concepts/expected-behavior-grammar.md`](docs/concepts/expected-behavior-grammar.md) for the DSL.
- **Active-branch workstream.** Start a workstream and every dashboard mutation commits to that branch; push and open a PR in one click. One PR per workstream, many commits — reviewers see the whole change in one place.
- **Registry as catalog.** Installing a curated `pbg-*` package adds it as a dependency; the dashboard's Discovered Processes/Types tables read live from `bigraph-schema`'s discovery walker — no manual `register_link()` boilerplate. See [`docs/conventions/discovery.md`](docs/conventions/discovery.md).
- **Composites are data.** Any `*.composite.yaml` / `*.composite.json` file in an installed package is a Composite spec — a declarative state document with typed, substitutable parameters — discoverable without importing simulator code. A decorator-based generator convention covers the dynamic case. See [`docs/conventions/composites.md`](docs/conventions/composites.md) and [`docs/conventions/composite_generators.md`](docs/conventions/composite_generators.md).
- **Visualizations are Steps.** `pbg_superpowers.visualization.Visualization` is a `process-bigraph` `Step` subclass: auto-discovered alongside Processes and Types, and wireable into Composite specs via the standard `inputs()/outputs()/update()` contract. See [`docs/conventions/visualizations.md`](docs/conventions/visualizations.md).

## Two repos

This plugin works with a sibling repo, [`pbg-template`](https://github.com/vivarium-collective/pbg-template), which `/pbg-workspace` clones to scaffold new workspaces. You can also use `pbg-template` directly via GitHub's "Use this template" button — its `template-init.sh` produces the same structure without this plugin.

## Tests

Two levels:

- **L1 (plugin internals)** — `pytest -q` from this repo.
- **L2 (workspace tests)** — `pytest tests/` from a workspace root, including registry checks and a drift detector.

CI is provided for both repos: `.github/workflows/plugin-ci.yml` here, and `workspace-ci.yml` in scaffolded workspaces via `pbg-template`.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — agent entry point.
- [`docs/concepts/`](docs/concepts/) — canonical data-model docs (start here when integrating with vivarium-dashboard).
- [`docs/conventions/`](docs/conventions/) — authoritative spec conventions (composites, generators, discovery, distribution, visualizations).
- [`docs/references/papers/`](docs/references/papers/) — the Process-Bigraph paper + supplement (formal semantics + framing).
- [`docs/superpowers/`](docs/superpowers/) — historical plans + specs from the build-out.
- [`docs/audits/`](docs/audits/) — dated snapshots (e.g. PyPI publication audits).

## License

MIT. See [`LICENSE`](LICENSE).

# pbg-superpowers

> **Canonical terminology** — see [`docs/concepts/process-bigraph-glossary.md`](docs/concepts/process-bigraph-glossary.md), anchored on Agmon & Spangler's supplement.

A Claude Code plugin for building **process-bigraph research projects**. It wraps simulators as composable process-bigraph units, composes them into larger models, and organizes the work into research workspaces with an interactive dashboard and HTML reports.

Use it to go from "I have a simulator" to "I have a reviewable, reproducible model project" — without writing the registry, packaging, and report boilerplate by hand.

> **🚧 In development.** The plugin and the [vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard) it drives are under active iteration; minor versions may reshape concepts or APIs.

## What pbg-superpowers is

From [Agmon & Spangler, 2026](docs/references/papers/agmon-spangler-2026-process-bigraphs-main.pdf) (§ Discussion, p. 14):

> A GitHub repository ... with a set of reusable AI agent skills that scaffold process wrapping and composition. These tools automate the creation of port-typed process interfaces and composite connection patterns, reducing manual effort and ambiguity.

Wrapped simulators include COMETS, CompuCell3D, Mem3DG, Smoldyn, VCell's finite-volume solver, Martini, and LAMMPS.

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

    /pbg-init my-project                       # scaffold a workspace
    cd my-project
    /pbg-server start                          # start the dashboard
    /pbg-list                                  # browse workspace catalog
    /pbg-study new pbg_chromosome_rep1.composites.dnaa-binding
    /pbg-study run-baseline dnaa-binding

Or — to add or wrap a new simulator first:

    /pbg-expert tellurium                      # wrap a simulator as a standalone pbg-* repo (+ tests, report, PR)
    /pbg-wrapper tellurium                     # ...or wrap it lightly inside the current workspace
    /pbg-expert metabolism cobra tellurium     # compose wrappers into a sibling composite repo
    /pbg-composer metabolism cobra tellurium   # ...or compose lightly inside the current workspace

## Skills

17 skills, grouped by purpose. See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md#skill--concept-map) for the full read/write surface.

### Wrap & compose simulators

| Skill | What it does |
|---|---|
| `/pbg-expert <tool>` | Wrap a simulator as a process-bigraph Process — full sibling `pbg-<tool>/` repo with Process class, tests, README, HTML report, and an open PR. The canonical wrap. |
| `/pbg-expert <name> <tools…>` | Compose two or more wrapped simulators into a sibling `pbg-<name>-composite/` repo with HTML report and PR. |
| `/pbg-wrapper <tool>` | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test stub. No sibling repo, no report. |
| `/pbg-composer <name> <tools…>` | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test stub. |
| `/pbg-suggest <request-id>` | Draft a repo name, PR title, or PR body in response to a dashboard Suggest request. |

### Workspace lifecycle & dashboard

| Skill | What it does |
|---|---|
| `/pbg-init <name>` | Scaffold a fresh workspace by cloning `pbg-template`. |
| `/pbg-workspace [subcmd]` | Workspace-level commands (status, history, etc.). |
| `/pbg-server [start\|stop\|status]` | Start/stop the dashboard server in the current workspace. Required precondition for the Studies skills. |
| `/pbg-status` | Print workspace health: server up? recent activity? |

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
| `/pbg-study <subcmd> …` | Full CRUD for **Studies** — baseline composites, variants, interventions, runs. 14 subcommands; see the [skill doc](skills/pbg-study/SKILL.md) or the [concept map](docs/concepts/vivarium-dashboard-model.md#the-concepts). |
| `/pbg-viz <study> <viz-name> '<description>'` | Generate a `Visualization` subclass from a natural-language description and attach it to a Study. |
| `/pbg-report [model\|--all]` | Regenerate `reports/index.html` after manual state changes. |

## Concepts

- **Workspace IS the model.** A workspace root contains `pbg_<slug>/`, `tests/`, and `workspace.yaml` directly. It owns the datasets, references, decision log, and dashboard for one model.
- **5-tab dashboard.** `Workspace inputs · Registry · Simulation Setup · Visualizations · Build Model`. The dashboard is the canonical UI for routine state changes; skills are the alternative for code-writing tasks that benefit from Claude. The server is opt-in — every skill works without it (Studies skills require it).
- **Studies have lists.** A Study's *baseline* is a **list** of composites; each *variant* references one of them via `base_composite` + carries flat `parameter_overrides`; *interventions* are text-only experimental conditions. See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md) for the canonical data model.
- **Active-branch workstream.** Start a workstream and every dashboard mutation commits to that branch; push and open a PR in one click. One PR per workstream, many commits — reviewers see the whole change in one place.
- **Registry as catalog.** Installing a curated `pbg-*` package adds it as a dependency; the dashboard's Discovered Processes/Types tables read live from `bigraph_schema`'s discovery walker — no manual `register_link()` boilerplate. See [`docs/conventions/discovery.md`](docs/conventions/discovery.md).
- **Composites are data.** Any `*.composite.yaml` / `*.composite.json` file in an installed package is a composite spec — a declarative state document with typed, substitutable parameters — discoverable without importing simulator code. A decorator-based generator convention covers the dynamic case. See [`docs/conventions/composites.md`](docs/conventions/composites.md) and [`docs/conventions/composite_generators.md`](docs/conventions/composite_generators.md).
- **Visualizations are Steps.** `pbg_superpowers.visualization.Visualization` is a `process_bigraph.Step` subclass: auto-discovered alongside Processes and Types, and wireable into Composite specs via the standard `inputs()/outputs()/update()` contract. See [`docs/conventions/visualizations.md`](docs/conventions/visualizations.md).

## Two repos

This plugin works with a sibling repo, [`pbg-template`](https://github.com/vivarium-collective/pbg-template), which `/pbg-init` and `/pbg-workspace` clone to scaffold new workspaces. You can also use `pbg-template` directly via GitHub's "Use this template" button — its `template-init.sh` produces the same structure without this plugin.

## Tests

Two levels:

- **L1 (plugin internals)** — `pytest -q` from this repo.
- **L2 (workspace tests)** — `pytest tests/` from a workspace root, including registry checks and a drift detector.

CI is provided for both repos: `.github/workflows/plugin-ci.yml` here, and `workspace-ci.yml` in scaffolded workspaces via `pbg-template`.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — agent entry point.
- [`docs/concepts/`](docs/concepts/) — canonical data-model docs (start here when integrating with vivarium-dashboard).
- [`docs/conventions/`](docs/conventions/) — authoritative spec conventions (composites, generators, discovery, distribution, visualizations).
- [`docs/superpowers/`](docs/superpowers/) — historical plans + specs from the build-out.
- [`docs/audits/`](docs/audits/) — dated snapshots (e.g. PyPI publication audits).

## License

MIT. See [`LICENSE`](LICENSE).

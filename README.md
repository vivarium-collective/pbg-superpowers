# pbg-superpowers

A Claude Code plugin for building **process-bigraph research projects**.
Scaffold a workspace, walk a canonical PR flow, plan multi-phase model
extensions, and produce interactive HTML reports.

## Install

(inside Claude Code:)

    /plugin install pbg-superpowers
    /reload-plugins

## Quick start

(inside Claude Code:)

    /plugin install pbg-superpowers
    /reload-plugins
    /pbg-workspace my-research-workspace
    cd ~/code/my-research-workspace
    bash scripts/serve.sh    # opens the 5-tab dashboard

In the dashboard:

1. **Workspace inputs** — drop in datasets, references (PDFs auto-extract metadata), and expert docs.
2. **Registry** — browse curated pbg-* modules, click Install on the ones you want. Each install adds a submodule, pip-installs into the venv, appends to pyproject.toml deps, and shows up in the Discovered Processes/Types tables.
3. **Simulation Setup** — pick observables to track and define simulation run configs.
4. **Visualizations** — write a name + natural-language description; click Create to invoke `/pbg-viz <name>`, which generates a Plotly/matplotlib function. Stage with "Add to project", commit when ready.
5. **Build Model** — start phases, drive each with `/pbg-phase <n>` from Claude Code, evaluate gates, accumulate commits on a single workstream branch.

Every dashboard mutation lands on your **active workstream branch** (one branch per workstream). When you're ready to share, click **Push** and **Create PR** in the sticky strip at the top — your co-workers review the whole accumulated change in one PR.

## Two repos

This plugin works with a sibling repo, [`pbg-template`](https://github.com/vivarium-collective/pbg-template),
which `/pbg-workspace` clones to scaffold new workspaces. You can also use
`pbg-template` directly via GitHub's "Use this template" button — the
`template-init.sh` in that repo produces the same structure without
requiring this plugin.

## Skills

| Skill | Stage | Repo target | Responsibility |
|---|---|---|---|
| `/pbg-workspace` | bootstrap | workspace | Scaffold a workspace by cloning `pbg-template` |
| `/pbg-server [start\|stop\|status]` | any | workspace | Local dashboard (5 tabs + workstream strip + branch timeline) |
| `/pbg-report` | any | workspace | Regenerate `reports/index.html` after manual state changes |
| `/pbg-phase <n>` | per phase | workspace | Drive phase n: walk Implementation Tasks, write code + tests, run gate |
| `/pbg-viz <name>` | per viz | workspace | Read `.pbg/viz-requests/<name>.md` and generate a Plotly/matplotlib `visualize()` function |
| `/pbg-package <repo>` | aux | any pbg-* repo | Audit a pbg-* repo for discovery-contract compliance (pyproject.toml, deps, subclasses, install smoke) |
| `/pbg-expert <tool>` *(vendored)* | aux | sibling pbg-* repo | Wrap a single simulator as `pbg-<tool>` |
| `/pbg-composer <name> <tools…>` *(vendored)* | aux | sibling pbg-composite repo | Compose pbg-* wrappers |

## Architecture

- **Workspace IS the model.** The workspace root contains `pbg_<slug>/`, `tests/`, `phases/`, and `workspace.yaml` directly. The workspace owns datasets, references, decision log, and the dashboard.
- **5-tab dashboard.** `Workspace inputs · Registry · Simulation Setup · Visualizations · Build Model`. Each tab is the canonical UI for that part of the workflow. Skills are the alternative for code-writing tasks that benefit from Claude.
- **Active-branch workstream model.** Click *Start workstream* in the sticky strip below the menu; every dashboard mutation commits to that branch. *Push* + *Create PR* one-click via the strip. One PR per workstream, many commits — co-workers review the whole accumulated change in one place.
- **Registry as catalog.** `scripts/_catalog/modules.json` lists curated pbg-* packages. Install adds a submodule, pip-installs into `.venv`, and appends to `pyproject.toml` `[project.dependencies]`. The Discovered Processes/Types tables read live from `bigraph_schema.package.discover` — no manual `register_link()` boilerplate needed. See [docs/conventions/discovery.md](docs/conventions/discovery.md).
- **Visualization-as-description.** A visualization is `{name, description}` in `workspace.yaml`. Create writes a request file; `/pbg-viz <name>` generates a Plotly/matplotlib `visualize()` function with a `_demo()` helper; Add to project stages it; Commit lands `pbg_<slug>/visualizations/<name>.py` on the active branch.
- **Phase template is first-class.** Each phase lives in `phases/phase-N.md` at the workspace root with YAML frontmatter (`status`, `prereq_phases`, `gate_passed`, `acceptance_tests`, …). The body uses your Phase Template format verbatim. The Build Model tab renders each phase with a Start phase / Evaluate gate action button.

## Tests

Three levels:

- **L1 (plugin internals)** — `pytest` from this repo
- **L2 (workspace lint)** — `python scripts/lint-workspace.py` inside any scaffolded workspace
- **L3 (workspace tests)** — `pytest tests/` from the workspace root, including `test_core_integration.py` (process/type registry checks + drift detector) and `test_phases.py` (auto-generated from phase frontmatter)

CI workflows are provided for both repos:

- `.github/workflows/plugin-ci.yml` (this repo)
- `.github/workflows/workspace-ci.yml` (in scaffolded workspaces, via `pbg-template`)

## Design

See `docs/superpowers/specs/2026-05-09-pbg-project-template-design.md`
in the brainstorming repo for the full architectural spec.

## License

MIT (or your-license-here).

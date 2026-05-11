# pbg-superpowers

> **🚧 In development.** This plugin is evolving rapidly. The skills marked **Stable** below
> are usable today; the rest (workspace bootstrap, dashboard, phases, visualization codegen,
> package audit) are under active iteration and may change shape between minor versions.

A Claude Code plugin for building **process-bigraph research projects**.
Scaffold a workspace, walk a canonical PR flow, plan multi-phase model
extensions, and produce interactive HTML reports.

## Install

(inside Claude Code:)

    /plugin install pbg-superpowers
    /reload-plugins

## Quick start

Wrap a simulator as a standalone pbg-* package:

    /pbg-expert tellurium

Or wrap it lightly inside an existing workspace:

    cd ~/code/my-workspace
    /pbg-wrapper tellurium

Compose multiple wrappers:

    /pbg-expert metabolism cobra tellurium       # heavy: new sibling composite repo
    /pbg-composer metabolism cobra tellurium     # light: inside current workspace

The workspace-bootstrap + dashboard skills (`/pbg-workspace`, `/pbg-server`,
`/pbg-report`, `/pbg-phase`, `/pbg-viz`, `/pbg-package`) are still in development
— see the table above.

## Two repos

This plugin works with a sibling repo, [`pbg-template`](https://github.com/vivarium-collective/pbg-template),
which `/pbg-workspace` clones to scaffold new workspaces. You can also use
`pbg-template` directly via GitHub's "Use this template" button — the
`template-init.sh` in that repo produces the same structure without
requiring this plugin.

## Skills

### Stable — recommended for current use

| Skill | Repo target | What it does |
|---|---|---|
| `/pbg-expert <tool>` | new `pbg-<tool>/` sibling | Wrap a simulator as a process-bigraph Process: scaffolds a full sibling repo with Process class, tests, README, HTML report, and an open PR. The heavy/canonical wrap. |
| `/pbg-expert <name> <tools…>` | new `pbg-<name>-composite/` sibling | Compose two or more wrapped simulators into a sibling composite repo, with HTML report and PR. Same heavy flow as the single-tool form. |
| `/pbg-wrapper <tool>` | current workspace | Lightweight in-workspace wrap. Writes `pbg_<slug>/processes/<tool>.py` + a test stub. No sibling repo, no report — good for incremental experimentation. |
| `/pbg-composer <name> <tools…>` | current workspace | Lightweight in-workspace composite. Writes `pbg_<slug>/composites/<name>.py` + test stub referencing already-installed wrapper packages. |
| `/pbg-suggest <request-id>` | current workspace | Draft a Claude-suggested repo name, PR title, or PR body in response to a dashboard Suggest button request. Writes the response to `.pbg/agent-responses/<id>.json`; dashboard polls and fills the input automatically. |

### In development

These ship today but their interfaces are still moving:

| Skill | What it does |
|---|---|
| `/pbg-workspace <name>` | Scaffold a workspace by cloning pbg-template |
| `/pbg-server [start\|stop\|status]` | Local dashboard (5 tabs + workstream strip + branch timeline) |
| `/pbg-report` | Regenerate `reports/index.html` after manual state changes |
| `/pbg-phase <n>` | Drive phase n inside a workspace |
| `/pbg-viz <name>` | Generate a Plotly/matplotlib `visualize()` function from a description |
| `/pbg-package <repo>` | Audit a pbg-* repo for discovery-convention compliance |

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

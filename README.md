# pbg-superpowers

A Claude Code plugin for building **process-bigraph research projects**.
Scaffold a workspace, walk a canonical PR flow, plan multi-phase model
extensions, and produce interactive HTML reports.

## Install

(inside Claude Code:)

    /plugin install pbg-superpowers
    /reload-plugins

## Quick start

    /pbg-workspace my-research-workspace
    cd ~/code/my-research-workspace
    # Open the dashboard — register imports, datasets, references, expert docs, observables, visualizations
    bash scripts/serve.sh
    # When ready to build a phase, use the skill:
    /pbg-phase 1

Optional dashboard server (for live phase-tracker updates):

    /pbg-server start
    # open the printed URL — live guidance + phase tracker

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
| `/pbg-server [start\|stop\|status]` | any | workspace | Local dashboard (opt-in; opens browser-based UI for inputs + lifecycle) |
| `/pbg-report` | any | workspace | Regenerate dashboard `reports/index.html` after manual state changes |
| `/pbg-phase <n>` | per phase | workspace | Drive phase n: walk Implementation Tasks, dispatch /pbg-expert if needed, write code + tests, run gate |
| `/pbg-expert <tool>` *(vendored)* | aux | sibling pbg-* repo | Wrap a single simulator as `pbg-<tool>` |
| `/pbg-composer <name> <tools…>` *(vendored)* | aux | sibling pbg-composite repo | Compose pbg-* wrappers |

## Architecture

- **Workspace IS the model.** The workspace root contains `pbg_<slug>/`, `tests/`, `phases/`, and `workspace.yaml` directly — no per-model submodule nesting. The workspace owns datasets, references, decision log, and the dashboard.
- **Dashboard is the primary UI for data inputs.** Loading imports, datasets, references, expert docs, observables, and visualizations all happen in the browser dashboard (`bash scripts/serve.sh`). Skills are reserved for code-writing work that benefits from Claude's assistance.
- **Reports are progressive enhancement.** `<workspace>/reports/index.html` works as a static page; if `/pbg-server` is running, the same file gains live phase-tracker updates.
- **Phase template is first-class.** Each phase lives in `phases/phase-N.md` at the workspace root with YAML frontmatter (`status`, `prereq_phases`, `gate_passed`, `acceptance_tests`, `parameters_added`, `deliverables`, `open_questions`). The body uses your Phase Template format verbatim.
- **Core/type registry is tested AND reported.** The workspace has tests that assert `build_core()` registers expected processes/types and a registry-snapshot drift detector. The same data drives the dashboard's Process Registry and Type Registry panels.
- **Auto-discovery is the registration model.** `pbg-*` packages don't need
  manual `register_link()` boilerplate — see [docs/conventions/discovery.md](docs/conventions/discovery.md).

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

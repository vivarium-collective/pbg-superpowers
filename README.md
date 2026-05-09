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
    /pbg-add-model ecoli-replication --remote git@github.com:you/ecoli-replication.git
    /pbg-pull-processes ecoli-replication
    /pbg-data ecoli-replication
    /pbg-expert-input ecoli-replication
    /pbg-baseline ecoli-replication
    /pbg-phase-plan ecoli-replication
    /pbg-phase 1
    /pbg-phase 2

Optional dashboard:

    /pbg-server start
    # open the printed URL — live guidance + phase tracker

## Two repos

This plugin works with a sibling repo, [`pbg-template`](https://github.com/eagmon/pbg-template),
which `/pbg-workspace` clones to scaffold new workspaces. You can also use
`pbg-template` directly via GitHub's "Use this template" button — the
`template-init.sh` in that repo produces the same structure without
requiring this plugin.

## Skills

| Skill | Stage | Repo target | Responsibility |
|---|---|---|---|
| `/pbg-workspace` | 0 | workspace | Scaffold a workspace by cloning `pbg-template` |
| `/pbg-add-model <name>` | 1+2 | both | Register a new model (cross-repo coordinated) |
| `/pbg-pull-processes <model>` | 3 | model | Install pbg-* deps; dispatch `/pbg-expert` for missing |
| `/pbg-data <model>` | 4+5 | workspace | Datasets + paper references curation |
| `/pbg-expert-input <model>` | 6 | model | Capture expectations as `if X then Y` acceptance tests |
| `/pbg-baseline <model>` | 7 | model | Build minimal Composite (dispatches `/pbg-composer`) |
| `/pbg-phase-plan <model>` | 8 | model | Lay out multi-phase plan |
| `/pbg-phase <n>` | 9..N | model | Implement one phase, run gate |
| `/pbg-server [start\|stop\|status]` | any | workspace | Local dashboard (opt-in) |
| `/pbg-report` | any | workspace + per-model | Regenerate dashboards |
| `/pbg-expert <tool>` *(vendored)* | aux | sibling pbg-* repo | Wrap a single tool as `pbg-<tool>` |
| `/pbg-composer <name> <tools…>` *(vendored)* | aux | sibling pbg-composite repo | Compose pbg-* wrappers |

## Architecture

- **Workspace = monorepo + git submodules.** Each model lives under `models/<name>/` as its own git submodule. The workspace owns datasets, references, decision log, and the workspace-level dashboard.
- **Stage skills follow a 9-phase contract** (see `docs/superpowers/specs/`): pre-flight → branch → walkthrough → edits + commits → PR_BODY → workspace.yaml update → /pbg-report → gh handoff.
- **Reports are progressive enhancement.** `<workspace>/reports/index.html` works as a static page; if `/pbg-server` is running, the same file gains live phase-tracker updates and an in-page "guidance band" that mirrors the active stage skill's prompts.
- **Phase template is first-class.** Each phase lives in `phases/phase-N.md` with YAML frontmatter (`status`, `prereq_phases`, `gate_passed`, `acceptance_tests`, `parameters_added`, `deliverables`, `open_questions`). The body uses your Phase Template format verbatim.
- **Core/type registry is tested AND reported.** Every model has L3 tests that assert `build_core()` registers expected processes/types and a registry-snapshot drift detector. The same data drives the dashboard's Process Registry and Type Registry panels.

## Tests

Four levels:

- **L1 (plugin internals)** — `pytest` from this repo (~68 tests)
- **L2 (workspace lint)** — `python scripts/lint-workspace.py` inside any scaffolded workspace
- **L3 (per-model)** — `pytest` from inside `models/<name>/`, including `test_core_integration.py` (process/type registry checks + drift detector)
- **L4 (phase acceptance + gate)** — `pytest models/<name>/tests/test_phases.py`, auto-generated from phase frontmatter

CI workflows are provided for all three repos:

- `.github/workflows/plugin-ci.yml` (this repo)
- `.github/workflows/workspace-ci.yml` (in scaffolded workspaces, via `pbg-template`)
- `.github/workflows/model-ci.yml` (in each model submodule, via the model template)

## Design

See `docs/superpowers/specs/2026-05-09-pbg-project-template-design.md`
in the brainstorming repo for the full architectural spec.

## License

MIT (or your-license-here).

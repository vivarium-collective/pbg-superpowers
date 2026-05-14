# pbg-superpowers

A Claude Code plugin for building **process-bigraph research projects**. It wraps
simulators as composable process-bigraph units, composes them into larger models,
and organizes that work into multi-phase research workspaces with an interactive
dashboard and HTML reports.

Use it to go from "I have a simulator" to "I have a reviewable, reproducible,
multi-phase model project" — without writing the registry, packaging, and report
boilerplate by hand.

> **🚧 In development.** Skills marked **Stable** in the table below are usable
> today. The rest are under active iteration and may change shape between minor
> versions.

## Install

Inside Claude Code:

    /plugin install pbg-superpowers
    /reload-plugins

## Quick start

    /pbg-expert tellurium                      # wrap a simulator as a standalone pbg-* repo (+ tests, report, PR)
    /pbg-wrapper tellurium                     # ...or wrap it lightly inside the current workspace
    /pbg-expert metabolism cobra tellurium     # compose wrappers into a sibling composite repo
    /pbg-composer metabolism cobra tellurium   # ...or compose lightly inside the current workspace

## Skills

| Skill | Maturity | Target | What it does |
|---|---|---|---|
| `/pbg-expert <tool>` | Stable | new `pbg-<tool>/` sibling repo | Wrap a simulator as a process-bigraph Process — full repo with Process class, tests, README, HTML report, and an open PR. The canonical wrap. |
| `/pbg-expert <name> <tools…>` | Stable | new `pbg-<name>-composite/` sibling repo | Compose two or more wrapped simulators into a sibling composite repo, with HTML report and PR. |
| `/pbg-wrapper <tool>` | Stable | current workspace | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test stub. No sibling repo, no report. |
| `/pbg-composer <name> <tools…>` | Stable | current workspace | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test stub. |
| `/pbg-suggest <request-id>` | Stable | current workspace | Draft a repo name, PR title, or PR body in response to a dashboard Suggest request. |
| `/pbg-workspace <name>` | In dev | new workspace dir | Scaffold a workspace by cloning `pbg-template`. |
| `/pbg-server [start\|stop\|status]` | In dev | current workspace | Run the local 5-tab dashboard server. |
| `/pbg-report [model\|--all]` | In dev | current workspace | Regenerate `reports/index.html` after manual state changes. |
| `/pbg-phase <n>` | In dev | current workspace | Drive phase _n_ of model development — code, tests, and the phase gate. |
| `/pbg-viz <name>` | In dev | current workspace | Generate a `Visualization` subclass from a natural-language description. |
| `/pbg-explore <spec-id>` | In dev | current workspace | Open the dashboard's Composite Explorer focused on one composite spec. |
| `/pbg-package <repo>` | In dev | external pbg-* repo | Audit a `pbg-*` repo for discovery- and packaging-convention compliance. |

## Concepts

- **Workspace IS the model.** A workspace root contains `pbg_<slug>/`, `tests/`,
  `phases/`, and `workspace.yaml` directly. It owns the datasets, references,
  decision log, and dashboard for one model.
- **5-tab dashboard.** `Workspace inputs · Registry · Simulation Setup ·
  Visualizations · Build Model`. The dashboard is the canonical UI for routine
  state changes; skills are the alternative for code-writing tasks that benefit
  from Claude. The server is opt-in — every skill works without it.
- **Active-branch workstream.** Start a workstream and every dashboard mutation
  commits to that branch; push and open a PR in one click. One PR per workstream,
  many commits — reviewers see the whole change in one place.
- **Registry as catalog.** Installing a curated `pbg-*` package adds it as a
  dependency; the dashboard's Discovered Processes/Types tables read live from
  `bigraph_schema`'s discovery walker — no manual `register_link()` boilerplate.
  See [docs/conventions/discovery.md](docs/conventions/discovery.md).
- **Composites are data.** Any `*.composite.yaml` / `*.composite.json` file in an
  installed package is a composite spec — a declarative state document with typed,
  substitutable parameters — discoverable without importing simulator code. A
  decorator-based generator convention covers the dynamic case. See
  [docs/conventions/composites.md](docs/conventions/composites.md).
- **Visualizations are Steps.** `pbg_superpowers.visualization.Visualization` is a
  `process_bigraph.Step` subclass: auto-discovered alongside Processes and Types,
  and wireable into Composite specs via the standard `inputs()/outputs()/update()`
  contract. See [docs/conventions/visualizations.md](docs/conventions/visualizations.md).
- **Phases are first-class.** Each phase is a `phases/phase-N.md` file with YAML
  frontmatter (`status`, `prereq_phases`, `gate_passed`, `acceptance_tests`, …).
  The Build Model tab renders each with Start phase / Evaluate gate actions.

## Two repos

This plugin works with a sibling repo,
[`pbg-template`](https://github.com/vivarium-collective/pbg-template), which
`/pbg-workspace` clones to scaffold new workspaces. You can also use `pbg-template`
directly via GitHub's "Use this template" button — its `template-init.sh` produces
the same structure without this plugin.

## Tests

Three levels:

- **L1 (plugin internals)** — `pytest` from this repo.
- **L2 (workspace lint)** — `python scripts/lint-workspace.py` inside a scaffolded workspace.
- **L3 (workspace tests)** — `pytest tests/` from a workspace root, including registry
  checks, a drift detector, and `test_phases.py` auto-generated from phase frontmatter.

CI is provided for both repos: `.github/workflows/plugin-ci.yml` here, and
`workspace-ci.yml` in scaffolded workspaces via `pbg-template`.

## Design

See `docs/superpowers/specs/2026-05-09-pbg-project-template-design.md` for the full
architectural spec.

## License

MIT (or your-license-here).

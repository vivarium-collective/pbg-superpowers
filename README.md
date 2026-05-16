# pbg-superpowers

A Claude Code plugin for building **multiscale models in the Process Bigraph framework**. Ships 11 `/pbg-*` skills that scaffold the mechanical parts of compositional modeling — wrapping a simulator as a typed Process, composing Processes into a Composite, organizing the work as a reproducible workspace, and managing studies + runs + visualizations through a local dashboard.

For **computational biologists** who want their models to be reusable, recombinable, and runnable by others — without writing the registry, packaging, schema, and report boilerplate by hand. Framework background: [Agmon & Spangler (2026)](docs/references/papers/agmon-spangler-2026-process-bigraphs-main.pdf).

## Install

Two parts — the Claude Code plugin (the skills) and the Python package the skills call into. Both are required.

    # 1. Plugin
    /plugin marketplace add vivarium-collective/pbg-superpowers
    /plugin install pbg-superpowers
    /reload-plugins

    # 2. Python package
    pip install pbg-superpowers

Verify with `/help` — the `/pbg-*` skills should be listed. For local development, point Claude at a working tree with `claude --plugin-dir /path/to/pbg-superpowers` and `pip install -e .`.

## Getting Started

Two supported paths. Both end at the same dashboard over the same workspace files — choose based on whether you want Claude in the loop.

### Path A — Dashboard only (no AI)

For testers evaluating the UI against an existing or scaffold-only workspace. No Claude Code required.

    pip install vivarium-dashboard
    # scaffold a workspace from pbg-template (GitHub "Use this template" or git clone)
    bash use-this-template-init.sh
    vivarium-dashboard serve --workspace .

Open the printed URL and browse the seven tabs — Registry, Composites, Studies, Investigations, Visualizations, Decisions, Runs. Create studies and investigations directly through the UI. Scaffolding details in the [pbg-template](https://github.com/vivarium-collective/pbg-template) README; serving details (ports, multi-workspace) in the [vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard) README.

### Path B — Dashboard + AI agent (pbg-superpowers integration)

The primary path for this repo. You drive the workspace by talking to Claude; Claude writes the typed Python, YAML, and visualization code; the dashboard reflects state in real time.

**How to install**

1. Install [Claude Code](https://claude.com/claude-code) if you haven't already.
2. From inside Claude Code:

        /plugin marketplace add vivarium-collective/pbg-superpowers
        /plugin install pbg-superpowers
        /reload-plugins

3. Install the Python package the skills call:

        pip install pbg-superpowers

Verify with `/help` — the `/pbg-*` skills should be listed.

**How to get started**

1. Scaffold a workspace (with an upstream model repo, or standalone if you omit `--upstream`):

        /pbg-workspace my-project --upstream <owner/repo>
        cd my-project

2. Boot the dashboard — Claude will print the local URL:

        /pbg-server start

3. Start authoring in natural language. Ask Claude to wrap a simulator (`/pbg-expert <tool>` for a sibling package, or `/pbg-expert --lightweight <tool>` in-workspace), compose a model (`/pbg-expert <name> <tools…>`), or design a study (`/pbg-study new`).

**What to expect**

You interact in natural language — you don't write the boilerplate. Claude authors the typed Process/Composite Python, the study YAML, the Visualization Step, and the tests, while you steer at the level of "wrap this solver," "compose these two," "design a study around this question." Every dashboard mutation Claude makes lands as a commit on your active workstream branch, so you get a full git audit trail and can review or revert any change. You can fall back to the dashboard UI for any of these tasks at any time — both paths share the same files. A common first session: ask Claude to wrap a tool you already know (an ODE solver, a COBRA model, a custom integrator) → run a quick simulation → ask it to draft a Study around a question you care about → it proposes follow-up Studies after the first one completes. The overall loop is **Design → Build → Simulate → Evaluate → Decide**, and Claude helps at each phase.

Full skill catalog: [`docs/skills.md`](docs/skills.md).

## Concepts

- **Workspace IS the model.** A git repo containing the model's Python package, tests, references, decisions log, and a `workspace.yaml`. The unit of reproducibility — clone a workspace, run it, get the same answer.
- **Study.** A self-contained research unit — purpose, baseline composite(s), simulations, readouts, behavior tests, conclusion — moving through five phases (Design → Build → Simulate → Evaluate → Decide). Each phase has a distinct deliverable. See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md).
- **Composite.** A typed graph of Processes wired to shared stores; itself a Process, so models compose recursively. JSON-serializable, so composites can be stored, exchanged, and executed across environments. See [`docs/conventions/composites.md`](docs/conventions/composites.md).
- **Visualization.** A `Step` subclass auto-discovered alongside Processes; wireable into Composites and attachable to Studies. Generated from a natural-language description via `/pbg-viz`. See [`docs/conventions/visualizations.md`](docs/conventions/visualizations.md).

## Skills

11 skills, grouped by purpose (wrap & compose · workspace lifecycle · catalog · run & study). See [`docs/skills.md`](docs/skills.md) for the full catalog.

## Companion repos

- **[pbg-template](https://github.com/vivarium-collective/pbg-template)** — the workspace scaffold cloned by `/pbg-workspace`. Use the template directly if you want a workspace without the Claude Code plugin.
- **[vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard)** — the local web UI the skills drive. Browse composites, run studies, render visualizations.

## Reference

- [`CLAUDE.md`](CLAUDE.md) — agent entry point.
- [`docs/concepts/`](docs/concepts/) — canonical data-model and terminology.
- [`docs/conventions/`](docs/conventions/) — authoritative specs for composites, generators, discovery, distribution, visualizations.
- [`docs/references/papers/`](docs/references/papers/) — the Process-Bigraph paper + supplement.

## Tests

Two levels: `pytest -q` from this repo for plugin internals, and `pytest tests/` from a scaffolded workspace for workspace-level checks. CI runs both — `.github/workflows/plugin-ci.yml` here, and `workspace-ci.yml` shipped with each new workspace via [pbg-template](https://github.com/vivarium-collective/pbg-template).

## Status

In active beta. APIs may change before 1.0.

## License

MIT. See [`LICENSE`](LICENSE).

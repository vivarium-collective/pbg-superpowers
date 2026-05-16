# pbg-superpowers

A Claude Code plugin for building **multiscale models in the Process Bigraph framework**. Ships 17 `/pbg-*` skills that scaffold the mechanical parts of compositional modeling — wrapping a simulator as a typed Process, composing Processes into a Composite, organizing the work as a reproducible workspace, and managing studies + runs + visualizations through a local dashboard.

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

## Quick start

    /pbg-workspace my-project --upstream <owner/repo>   # scaffold a workspace
    cd my-project
    /pbg-server start                                   # start the local dashboard
    /pbg-list                                           # browse the catalog
    /pbg-study new <pkg.composites.my-composite>        # create a Study
    /pbg-study run-baseline my-composite                # run it

To wrap a new mechanism first, use `/pbg-expert <tool>` (full sibling repo with tests, report, and PR) or `/pbg-wrapper <tool>` (lightweight in-workspace wrap).

## Concepts

- **Workspace IS the model.** A git repo containing the model's Python package, tests, references, decisions log, and a `workspace.yaml`. The unit of reproducibility — clone a workspace, run it, get the same answer.
- **Study.** A self-contained research unit — purpose, baseline composite(s), simulations, readouts, behavior tests, conclusion — moving through five phases (Design → Build → Simulate → Evaluate → Decide). Each phase has a distinct deliverable. See [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md).
- **Composite.** A typed graph of Processes wired to shared stores; itself a Process, so models compose recursively. JSON-serializable, so composites can be stored, exchanged, and executed across environments. See [`docs/conventions/composites.md`](docs/conventions/composites.md).
- **Visualization.** A `Step` subclass auto-discovered alongside Processes; wireable into Composites and attachable to Studies. Generated from a natural-language description via `/pbg-viz`. See [`docs/conventions/visualizations.md`](docs/conventions/visualizations.md).

## Skills

17 skills, grouped by purpose (wrap & compose · workspace lifecycle · catalog · run & study). See [`docs/skills.md`](docs/skills.md) for the full catalog.

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

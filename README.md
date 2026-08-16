# viva-superpowers

> _Renamed from **pbg-superpowers** (pbg→viva rebrand, now complete). Old repo/marketplace paths redirect and the `/pbg-*` alias skills have been removed — use `/viva-*`. The `pbg-superpowers` PyPI dist and the `pbg_superpowers` import both remain only as thin back-compat shims that re-export `viva-superpowers`._

A Claude Code plugin for building **multiscale models in the Process Bigraph framework**. Ships 18 `/viva-*` skills that scaffold the mechanical parts of compositional modeling — wrapping a simulator as a typed Process, composing Processes into a Composite, organizing the work as a reproducible workspace, and managing studies + runs + visualizations through a local dashboard.

For **computational biologists** who want their models to be reusable, recombinable, and runnable by others — without writing the registry, packaging, schema, and report boilerplate by hand. Framework background: [Agmon & Spangler (2026)](docs/references/papers/agmon-spangler-2026-process-bigraphs-main.pdf).

## New here? Five minutes to a first result

You talk biology; Claude writes the typed plumbing. From inside [Claude Code](https://claude.com/claude-code):

    /plugin marketplace add vivarium-collective/viva-superpowers
    /plugin install viva-superpowers
    /reload-plugins
    pip install viva-superpowers        # the Python helpers the skills call

Then just describe what you want to model — in plain language:

> **"Scaffold a workspace called `demo`, wrap the Lotka–Volterra predator–prey equations as a process, and run it for 100 steps."**

Claude routes that through the skills automatically (`viva-orient` is auto-injected each session): `/viva-workspace demo` scaffolds the workspace → `/viva-workbench start` boots the dashboard and prints a local URL → `/viva-expert` wraps the equations as a typed Process → `/viva-run` executes it. Open the URL and you'll see the composite, its emitted trajectories, and a live run — a working process-bigraph model you never wrote the boilerplate for. From there: ask for a Study (`/viva-study`), a figure (`/viva-viz`), or wrap a real solver (an ODE integrator, a COBRA/FBA model).

That's the whole loop: **describe → Claude invokes the right `/viva-*` skill → the dashboard reflects it.** The rest of this README is reference.

## Install

Two parts — the Claude Code plugin (the skills) and the Python package the skills call into. Both are required.

    # 1. Plugin (from inside Claude Code)
    /plugin marketplace add vivarium-collective/viva-superpowers
    /plugin install viva-superpowers
    /reload-plugins

    # 2. Python package
    pip install viva-superpowers

Verify with `/help` — the `/viva-*` skills should be listed. For local development, point Claude at a working tree with `claude --plugin-dir /path/to/viva-superpowers` and `pip install -e .`.

> Maintainers only: a few rigor features (band provenance) also need **investigation-contracts**, which isn't on PyPI yet — install it editable: `pip install -e /path/to/investigation-contracts`. Everyday modeling doesn't require it.

## Getting Started

The primary path is **Claude in the loop** (Path A). A dashboard-only path with no AI is documented below it for UI testers. Both end at the same dashboard over the same workspace files.

### Path A — Dashboard + AI agent (the primary path)

You drive the workspace by talking to Claude; Claude writes the typed Python, YAML, and visualization code; the dashboard reflects state in real time. Install as above, then:

1. Scaffold a workspace (with an upstream model repo, or standalone if you omit `--upstream`):

        /viva-workspace my-project --upstream <owner/repo>
        cd my-project

2. Boot the dashboard — Claude will print the local URL:

        /viva-workbench start

3. Start authoring in natural language. Ask Claude to wrap a simulator (`/viva-expert <tool>` for a sibling package, or `/viva-expert --lightweight <tool>` in-workspace), compose a model (`/viva-expert <name> <tools…>`), or design a study (`/viva-study new`).

**What to expect**

You interact in natural language — you don't write the boilerplate. Claude authors the typed Process/Composite Python, the study YAML, the Visualization Step, and the tests, while you steer at the level of "wrap this solver," "compose these two," "design a study around this question." Every dashboard mutation Claude makes lands as a commit on your active workstream branch, so you get a full git audit trail and can review or revert any change. You can fall back to the dashboard UI for any of these tasks at any time — both paths share the same files. A common first session: ask Claude to wrap a tool you already know (an ODE solver, a COBRA model, a custom integrator) → run a quick simulation → ask it to draft a Study around a question you care about → it proposes follow-up Studies after the first one completes. The overall loop is **Design → Build → Simulate → Evaluate → Decide**, and Claude helps at each phase.

Full skill catalog: [`docs/skills.md`](docs/skills.md).

### Path B — Dashboard only (no AI)

For testers evaluating the UI against an existing or scaffold-only workspace. No Claude Code required.

    pip install vivarium-workbench
    # scaffold a workspace from viva-template (GitHub "Use this template" or git clone)
    bash use-this-template-init.sh
    vivarium-workbench serve --workspace .

Open the printed URL and browse the side-rail tabs — Workspace, Registry, Composites, Investigations, Visualizations, GitHub Branches, Simulations DB (the canonical set is owned by the [vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench); see `/viva-workbench`). Create studies and investigations directly through the UI. Scaffolding details in the [viva-template](https://github.com/vivarium-collective/viva-template) README; serving details (ports, multi-workspace) in the [vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench) README.

## Concepts

- **Workspace IS the model.** A git repo containing the model's Python package, tests, references, decisions log, and a `workspace.yaml`. The unit of reproducibility — clone a workspace, run it, get the same answer.
- **Study.** A self-contained research unit — purpose, baseline composite(s), simulations, readouts, behavior tests, conclusion — moving through five phases (Design → Build → Simulate → Evaluate → Decide). Each phase has a distinct deliverable. See [`docs/concepts/vivarium-workbench-model.md`](docs/concepts/vivarium-workbench-model.md).
- **Composite.** A typed graph of Processes wired to shared stores; itself a Process, so models compose recursively. JSON-serializable, so composites can be stored, exchanged, and executed across environments. See [`docs/conventions/composites.md`](docs/conventions/composites.md).
- **Visualization.** A `Step` subclass auto-discovered alongside Processes; wireable into Composites and attachable to Studies. Generated from a natural-language description via `/viva-viz`. See [`docs/conventions/visualizations.md`](docs/conventions/visualizations.md).

### Workspace vs composite-only repo

Two surfaces commonly get confused when a new user says "make this a viva-superpowers repo":

| Shape | Has `workspace.yaml`? | What lives in it | Driven by |
|---|---|---|---|
| **Workspace** | yes | `studies/`, `investigations/`, `notes/`, `references/`, `scripts/serve.sh`, plus the model's Python package | the vivarium-workbench + the `/viva-*` skills |
| **Composite-only repo** | no | a single Process or Composite package (e.g. `pbg-mem3dg`, `pbg-readdy`) — `pyproject.toml`, `pbg_<slug>/`, `tests/`, `demo/` | imported by one or more workspaces via `workspace.yaml.imports` |

A workspace can wrap or live beside one or more composite-only repos. Use `/viva-workspace --in-place` to promote an existing composite-only repo into a workspace branch (adds the workspace artifacts on top without clobbering the composite's existing files).

## Skills

18 skills, grouped by purpose (wrap & compose · workspace lifecycle · studies & runs · navigate & rigor). See [`docs/skills.md`](docs/skills.md) for the full catalog.

## Companion repos

- **[viva-template](https://github.com/vivarium-collective/viva-template)** — the workspace scaffold cloned by `/viva-workspace`. Use the template directly if you want a workspace without the Claude Code plugin.
- **[vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench)** — the local web UI the skills drive. Browse composites, run studies, render visualizations.

## Reference

- [`CLAUDE.md`](CLAUDE.md) — agent entry point.
- [`docs/concepts/`](docs/concepts/) — canonical data-model and terminology.
- [`docs/conventions/`](docs/conventions/) — authoritative specs for composites, generators, discovery, distribution, visualizations.
- [`docs/references/papers/`](docs/references/papers/) — the Process-Bigraph paper + supplement.

## Tests

Two levels: `pytest -q` from this repo for plugin internals, and `pytest tests/` from a scaffolded workspace for workspace-level checks. CI runs both — `.github/workflows/plugin-ci.yml` here, and `workspace-ci.yml` shipped with each new workspace via [viva-template](https://github.com/vivarium-collective/viva-template).

## Status

In active beta. APIs may change before 1.0.

## License

MIT. See [`LICENSE`](LICENSE).

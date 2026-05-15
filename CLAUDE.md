# pbg-superpowers — agent entry point

This is the Claude Code plugin that drives the [vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard) — a web UI for building and running process-bigraph simulation workspaces. Skills in this plugin read from the dashboard, write to it, and fill it out with content generated from user prompts.

## Start here

1. **Concept map: [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md)** — canonical vocabulary (Workspace · Study · Baseline · Variant · Intervention · Run · Visualization), on-disk shapes, the dashboard API surface, and which skill controls which concept. **Read this before invoking any Study/Baseline/Variant skill.**
2. **Conventions: [`docs/conventions/`](docs/conventions/)** — authoritative specs for composites, composite generators, discovery, distribution, and visualizations.
3. **README: [`README.md`](README.md)** — install + quick start for humans.

## Working preconditions

Every skill that touches the dashboard requires:
1. A workspace (a directory with `workspace.yaml` + `pbg_<pkg>/`). Create via `/pbg-init`.
2. The dashboard server running. Start via `/pbg-server start`. Skills read `.pbg/server/server-info` for the URL.

If either is missing, the skill should fail with a clear actionable error pointing the user at the missing precondition.

## Skill design conventions

- **Skill names** are kebab-case under `skills/<name>/SKILL.md`. Each skill is one file with YAML front-matter (`name`, `description`, `allowed-tools`, optionally `user-invocable: true` and `argument-hint`).
- **Vocabulary:** use **Study**, not "Investigation". The legacy term is kept only in on-disk v2 paths (`investigations/<name>/spec.yaml`) and one or two API body keys for back-compat.
- **API calls:** prefer `/api/study-*` endpoints over the v2 `/api/investigation-*` aliases. New skill code targets v3.
- **Body keys:** standardize on `study:` (not `investigation:`, not `name:` when the body has a separate entry-name field). The server's `_study_name_from_body` accepts all three but new code should send `study:`.
- **Subcommands** (for skills like `/pbg-study`) use kebab-case verbs: `new`, `set-objective`, `baseline-add`, `variant-set-params`, `run-baseline`, etc.

## Editing rules

- **Don't add features the plan doesn't call for.** Each skill has a tight scope; keep it.
- **One change per commit.** Rebasing/squashing later is fine; cohesive diffs are better than big PRs.
- **Tests live in `tests/`.** Most skills don't have unit tests (they're shell + curl); the Python package `pbg_superpowers/` does. Run `pytest -q` before committing Python changes.
- **Don't commit secrets, credentials, or workspace data** (no `.pbg/` state, no `workspace.yaml` from real workspaces).

## Common operations cheat-sheet

| Task | Command |
|---|---|
| Survey the workspace | `/pbg-list` |
| Open dashboard | `/pbg-server start` (then visit the URL) |
| Create a study | `/pbg-study new <composite-id>` |
| Add a baseline composite to a study | `/pbg-study baseline-add <study> --name <n> --composite <id>` |
| Add a variant of a baseline composite | `/pbg-study variant-add <study> --name <n> --base-composite <baseline-name> --params '<json>'` |
| Run a baseline composite | `/pbg-study run-baseline <study> [--composite <name>]` |
| Run a variant | `/pbg-study run-variant <study> --variant <name>` |
| Record a textual intervention | `/pbg-study intervention-add <study> --name <n> --description '<text>'` |
| Add a visualization | `/pbg-viz <study> <viz-name> '<description>'` |
| Render a study report | `/pbg-report <study>` |
| Run a composite directly (no Study) | `/pbg-run <composite-id> [--steps N]` |

For the full set of skill commands, see [`docs/concepts/vivarium-dashboard-model.md`](docs/concepts/vivarium-dashboard-model.md#skill--concept-map).

## Repo layout

```
pbg-superpowers/
├── .claude-plugin/        # plugin.json + marketplace.json (manifest format)
├── pbg_superpowers/       # Python package (schemas, visualizations, helpers)
├── server/                # the report-mirror server (NOT the dashboard — see pbg-server skill)
├── skills/                # 18 skill directories, one SKILL.md each
├── templates/             # Jinja templates for scaffolding workspaces + models
├── tests/                 # pytest suite for the Python package
├── docs/
│   ├── audits/            # dated snapshots (e.g. PyPI audit)
│   ├── concepts/          # canonical data-model docs (THIS ENTRY POINT)
│   ├── conventions/       # authoritative spec conventions
│   └── superpowers/       # historical plans + specs from the build-out
└── scripts/               # ops scripts (audit-pbg-catalog, update-scaffold-snapshot)
```

## When in doubt

- **What does this concept mean?** → `docs/concepts/vivarium-dashboard-model.md`.
- **How is a composite/generator/etc. structured?** → `docs/conventions/`.
- **How was this feature built?** → `docs/superpowers/plans/` (historical).
- **What's the right endpoint to call?** → the concept map's API tables.

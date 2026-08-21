# viva-superpowers — agent entry point

This is the Claude Code plugin that drives the [vivarium-workbench](https://github.com/vivarium-collective/vivarium-workbench) — a web UI for building and running process-bigraph simulation workspaces. Skills in this plugin read from the dashboard, write to it, and fill it out with content generated from user prompts.

## Start here

1. **Concept map: [`docs/concepts/vivarium-workbench-model.md`](docs/concepts/vivarium-workbench-model.md)** — canonical vocabulary (Workspace · Study · Baseline · Variant · Intervention · Run · Visualization), the 8-section canonical `study.yaml` (Pass 7), Decide-phase follow-up proposals (Pass 8), on-disk shapes, the dashboard API surface, and which skill controls which concept. **Read this before invoking any Study/Baseline/Variant skill.**
2. **Conventions: [`docs/conventions/`](docs/conventions/)** — authoritative specs for composites, composite generators, discovery, distribution, visualizations, and bespoke runner scripts.
3. **Skills catalog: [`docs/skills.md`](docs/skills.md)** — all 14 user-invocable `/viva-*` skills with one-line descriptions.
4. **README: [`README.md`](README.md)** — install + quick start for humans.

## Working preconditions

Every skill that touches the dashboard requires:
1. A workspace (a directory with `workspace.yaml` + a Python package, `viva_<pkg>/`). Create via `/viva-workspace`.
2. The dashboard server running. Start via `/viva-workbench start`. Skills read `.pbg/server/server-info` for the URL.

If either is missing, the skill should fail with a clear actionable error pointing the user at the missing precondition.

## Skill design conventions

- **Skill names** are kebab-case under `skills/<name>/SKILL.md`. Each skill is one file with YAML front-matter (`name`, `description`, `allowed-tools`, optionally `user-invocable: true` and `argument-hint`).
- **Vocabulary:** use **Study**, not "Investigation". The legacy term is kept only in on-disk v2 paths (`investigations/<name>/spec.yaml`) and one or two API body keys for back-compat.
- **API calls:** prefer `/api/study-*` endpoints over the v2 `/api/investigation-*` aliases. New skill code targets v3.
- **Body keys:** standardize on `study:` (not `investigation:`, not `name:` when the body has a separate entry-name field). The server's `_study_name_from_body` accepts all three but new code should send `study:`.
- **Subcommands** (for skills like `/viva-study`) use kebab-case verbs: `new`, `set-objective`, `baseline-add`, `variant-set-params`, `run-baseline`, `propose-followup`, `seed-from-followup`, etc. The `/viva-study` subcommand surface is organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide).

## Authored-content style (prose the skills write into a Study)

Skills fill Study/Investigation fields with generated prose — `question`, `claim`, `biological_summary`, `conclusion`, `findings[].*`, verdicts, report text. Write that prose in **normal sentence case**. Do **not** use ALL-CAPS words for emphasis: it renders as shouting in the report and the dashboard. Reserve capitals for genuine acronyms (FBA, DNA, ATP, ODE), unit symbols, and enum/status values (`PASS`, `FAIL`, `MIXED`; the Design/Build/Simulate/Evaluate/Decide phases). When a word genuinely needs emphasis, use markdown *italics*, not capitals.

The ALL-CAPS in these skills' *own* instructions (e.g. "BIAS TO EXECUTE", "HONEST OPEN QUESTION") is emphasis directed at **you, the agent** — it is not a style to copy into the content you author.

## Editing rules

- **Don't add features the plan doesn't call for.** Each skill has a tight scope; keep it.
- **One change per commit.** Rebasing/squashing later is fine; cohesive diffs are better than big PRs.
- **Tests live in `tests/`.** Most skills don't have unit tests (they're shell + curl); the Python package `viva_superpowers/` does. Run `pytest -q` before committing Python changes.
- **Don't commit secrets, credentials, or workspace data** (no `.pbg/` state, no `workspace.yaml` from real workspaces).
- **Cleanup PRs must spare `notes/` and `references/notes/` in workspaces.** Those directories hold the field records (friction logs, walkthroughs, agent transcripts, per-paper notes) that feed the next round of infrastructure improvements. A `chore(cleanup): …` PR that deletes anything under those paths is suspect — surface the deletion to the user and ask for per-file confirmation. See the scaffold's `notes/README.md` for the convention.

## Common operations cheat-sheet

| Task | Command |
|---|---|
| Survey the workspace | `/viva-catalog` (or `/viva-catalog list`) |
| Open dashboard | `/viva-workbench start` (then visit the URL) |
| Create a study | `/viva-study new <composite-id>` |
| Add a baseline composite to a study | `/viva-study baseline-add <study> --name <n> --composite <id>` |
| Add a variant of a baseline composite | `/viva-study variant-add <study> --name <n> --base-composite <baseline-name> --params '<json>'` |
| Run a baseline composite | `/viva-study run-baseline <study> [--composite <name>]` |
| Run a variant | `/viva-study run-variant <study> --variant <name>` |
| Run a bespoke runner script | `/viva-study run-script <study> [--entry <name>]` (reads `canonical_runs:` block) |
| Run all studies in an investigation | `/viva-investigation run <inv-slug> [--studies a,b] [--entry <name>]` (orchestrates `run-script` across members) |
| Wipe runtime output for a from-scratch rerun | `/viva-study clean <study> [--dry-run] [--include-out-paths]` (refuses to touch git-tracked files) |
| Record a textual intervention | `/viva-study intervention-add <study> --name <n> --description '<text>'` |
| Audit a study's Tests before locking (agentic loop) | `/viva-tests audit <study-slug>` |
| Drive the agentic model-building loop (question → validated model) | `/viva-model-build <study> [--autonomous]` |
| Benchmark the framework's model-building (score across variants) | `/viva-benchmark <suite> [--variant-label] [--score-only]` |
| Add a visualization | `/viva-viz <study> <viz-name> '<description>'` |
| Render a study report | `/viva-report <study>` |
| Run a composite directly (no Study) | `/viva-run <composite-id> [--steps N]` |
| Propose a Decide-phase follow-up study | `/viva-study propose-followup <study> --id <slug> --title '<t>' --motivation '<m>'` |
| Seed a new study from a follow-up proposal | `/viva-study seed-from-followup <parent-study> <proposal-id>` |

For the full set of skill commands, see [`docs/concepts/vivarium-workbench-model.md`](docs/concepts/vivarium-workbench-model.md#skill--concept-map).

## Repo layout

```
viva-superpowers/
├── .claude-plugin/        # plugin.json + marketplace.json (manifest format)
├── viva_superpowers/       # Python package (schemas, visualizations, helpers)
├── skills/                # user-invocable `/viva-*` skills + `/viva-init` (machine setup) + `/viva-suggest` (internal dashboard callback)
├── templates/             # Jinja templates for scaffolding workspaces + models
├── tests/                 # pytest suite for the Python package
├── docs/
│   ├── concepts/          # canonical data-model docs (THIS ENTRY POINT)
│   ├── conventions/       # authoritative spec conventions
│   └── references/        # PDF references (papers)
└── scripts/               # ops scripts (audit-pbg-repo, update-scaffold-snapshot)
```

## When in doubt

- **What does this concept mean?** → `docs/concepts/vivarium-workbench-model.md`.
- **How is a composite/generator/etc. structured?** → `docs/conventions/`.
- **What's the right endpoint to call?** → the concept map's API tables.

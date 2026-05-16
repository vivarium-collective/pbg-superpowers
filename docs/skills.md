# Skills catalog

17 skills grouped by purpose. Each entry links to the skill's `SKILL.md` for the full contract (front-matter, args, side effects).

## Wrap & compose

| Skill | What it does |
|---|---|
| [`/pbg-expert <tool>`](../skills/pbg-expert/SKILL.md) | Wrap a simulator as a Process — full sibling `pbg-<tool>/` repo with Process class, tests, README, HTML report, and an open PR. The canonical wrap. |
| [`/pbg-expert <name> <tools…>`](../skills/pbg-expert/SKILL.md) | Compose two or more wrapped simulators into a sibling `pbg-<name>-composite/` repo with HTML report and PR. |
| [`/pbg-wrapper <tool>`](../skills/pbg-wrapper/SKILL.md) | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test stub. No sibling repo, no report. |
| [`/pbg-composer <name> <tools…>`](../skills/pbg-composer/SKILL.md) | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test stub. |
| [`/pbg-suggest <request-id>`](../skills/pbg-suggest/SKILL.md) | Draft a repo name, PR title, or PR body in response to a dashboard Suggest request. |

## Workspace lifecycle & dashboard

| Skill | What it does |
|---|---|
| [`/pbg-workspace <name>`](../skills/pbg-workspace/SKILL.md) | Scaffold a fresh workspace — three modes: upstream-branch (clone an upstream model repo and create a workspace branch), standalone (clone `pbg-template`), or in-place (promote an existing checkout). |
| [`/pbg-server [start\|stop\|status]`](../skills/pbg-server/SKILL.md) | Start/stop the dashboard server in the current workspace. Required precondition for the Studies skills. |
| [`/pbg-status`](../skills/pbg-status/SKILL.md) | Print workspace health: is this a workspace? server up? recent activity? |

## Catalog & registry

| Skill | What it does |
|---|---|
| [`/pbg-install <pkg>`](../skills/pbg-install/SKILL.md) | Add a curated `pbg-*` package, install it, and refresh the workspace catalog. |
| [`/pbg-uninstall <pkg>`](../skills/pbg-uninstall/SKILL.md) | Remove an installed `pbg-*` package. |
| [`/pbg-list`](../skills/pbg-list/SKILL.md) | Browse the workspace catalog — composites, studies, registry. |
| [`/pbg-package <repo>`](../skills/pbg-package/SKILL.md) | Audit an external `pbg-*` repo for discovery- and packaging-convention compliance. |

## Run, explore, study

| Skill | What it does |
|---|---|
| [`/pbg-run <composite-id> [--steps N]`](../skills/pbg-run/SKILL.md) | Run a composite directly (no Study attached). |
| [`/pbg-explore <spec-id>`](../skills/pbg-explore/SKILL.md) | Open the dashboard's Composite Explorer focused on one composite. |
| [`/pbg-study <subcmd> …`](../skills/pbg-study/SKILL.md) | Full CRUD for **Studies** — baseline composites, variants, interventions, runs, behavior tests, follow-up proposals. Organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide). |
| [`/pbg-investigation <subcmd> …`](../skills/pbg-investigation/SKILL.md) | Manage **Investigations** — named collections of Studies grouped under a shared research question, with a cross-study dependency DAG. |
| [`/pbg-viz <study> <viz-name> '<description>'`](../skills/pbg-viz/SKILL.md) | Generate a `Visualization` subclass from a natural-language description and attach it to a Study. |
| [`/pbg-report [model\|--all]`](../skills/pbg-report/SKILL.md) | Regenerate `reports/index.html` after manual state changes. |

For the read/write surface each skill touches (which API endpoints, which on-disk files), see the [Skill ↔ concept map](concepts/vivarium-dashboard-model.md#skill--concept-map).

> The plugin also ships `/pbg-init`, a one-shot machine-setup installer that symlinks the skills into `~/.claude/skills/`. Not part of the workflow surface above.

# Skills catalog

15 user-facing skills (plus `/pbg-init` machine setup and one internal dashboard callback). Each entry links to the skill's `SKILL.md` for the full contract (front-matter, args, side effects). v0.9 consolidated the 17-skill v0.8 catalog — see the [migration table](#migration-from-v08) below.

## Wrap & compose

| Skill | What it does |
|---|---|
| [`/pbg-expert <tool>`](../skills/pbg-expert/SKILL.md) | Wrap a simulator as a Process — full sibling `pbg-<tool>/` repo with Process class, tests, README, HTML report, and a local commit. **Bridges the REAL tool by default** (keeps trying even when the build is hard); never silently downgrades. The canonical wrap. |
| [`/pbg-expert <name> <tools…>`](../skills/pbg-expert/SKILL.md) | Compose two or more wrapped simulators into a sibling `pbg-<name>-composite/` repo with HTML report and a local commit. |
| [`/pbg-expert --lightweight <tool>`](../skills/pbg-expert/SKILL.md#lightweight-mode) | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test. Still a **real bridge** (lazy-imports + drives the genuine tool); only the repo scaffolding is dropped. No sibling repo, no report. (Alias: `--in-workspace`. Replaces v0.8 `/pbg-wrapper`.) |
| [`/pbg-expert --lightweight <name> <tools…>`](../skills/pbg-expert/SKILL.md#lightweight-mode) | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test. (Replaces v0.8 `/pbg-composer`.) |
| [`/pbg-expert --reproduce <tool>`](../skills/pbg-expert/SKILL.md#reproduction-mode) | Opt-in: clean-room reimplement the tool's published algorithm as a labeled `<Tool>ReproductionProcess` (for when the real tool genuinely can't run here). Not the default. |
| [`/pbg-expert --mock <tool>`](../skills/pbg-expert/SKILL.md#mock-mode) | Opt-in: emit a non-functional `<Tool>MockProcess` placeholder (real ports, inert `update()`) for scaffolding/wiring only. Never a fallback for a hard build. Alias `--stub`. |

## Workspace lifecycle & dashboard

| Skill | What it does |
|---|---|
| [`/pbg-workspace <name>`](../skills/pbg-workspace/SKILL.md) | Scaffold a fresh workspace — three modes: upstream-branch (clone an upstream model repo and create a workspace branch), standalone (clone `pbg-template`), or in-place (promote an existing checkout). |
| [`/pbg-dashboard [start\|stop\|status\|open\|restart]`](../skills/pbg-dashboard/SKILL.md) | Start/stop/open the interactive vivarium-workbench (the side-rail-tabbed UI). The server the Studies skills depend on. Distinct from `/pbg-server`. |
| [`/pbg-server [start\|stop\|status]`](../skills/pbg-server/SKILL.md) | Start/stop the **report-mirror** server (serves `reports/index.html`, proxies stage-skill events). NOT the interactive dashboard — that's `/pbg-dashboard`. |
| [`/pbg-status`](../skills/pbg-status/SKILL.md) | Print workspace health: is this a workspace? server up? recent activity? Delegates the server-liveness section to `/pbg-server status`. |

## Catalog & registry

| Skill | What it does |
|---|---|
| [`/pbg-catalog [list]`](../skills/pbg-catalog/SKILL.md) | Browse the workspace catalog — composites, studies, registry. Default subcommand when no args. (Replaces v0.8 `/pbg-list`.) |
| [`/pbg-catalog install <pkg>`](../skills/pbg-catalog/SKILL.md#install) | Add a curated `pbg-*` package, install it, refresh the workspace catalog. (Replaces v0.8 `/pbg-install`.) |
| [`/pbg-catalog uninstall <pkg>`](../skills/pbg-catalog/SKILL.md#uninstall) | Remove an installed `pbg-*` package. (Replaces v0.8 `/pbg-uninstall`.) |

Maintainer-only: to audit an external `pbg-*` repo for discovery- and
packaging-convention compliance, run `python scripts/audit-pbg-repo.py <repo>`
from a pbg-superpowers checkout. (Replaces the v0.8 `/pbg-package` skill.)

## Provenance & citations

| Skill | What it does |
|---|---|
| [`/pbg-cite-bands <study-slug>`](../skills/pbg-cite-bands/SKILL.md) | Guided band-provenance extraction (spine stage #3b) — surface candidate evidence from expert PDFs for uncited acceptance bands, then write structured `cites`/`calibration_anchor` into `study.yaml` via a deterministic comment-preserving helper. |
| [`/pbg-biology-forward <study-slug>`](../skills/pbg-biology-forward/SKILL.md) | Biology-forward results authoring (spine stage #5) — run `populate_finding_observations` to fill quantitative slots (`evidence.observed`, `expected.range`, `divergence_factor`) from `computed_outcomes`, then guide the agent to author the mechanism prose (`statement`/`summary`/`explanation`/`status`) over that scaffold. |

## Run, explore, study

| Skill | What it does |
|---|---|
| [`/pbg-run <composite-id> [--steps N]`](../skills/pbg-run/SKILL.md) | Run a composite directly (no Study attached). |
| [`/pbg-explore <spec-id>`](../skills/pbg-explore/SKILL.md) | Open the dashboard's Composite Explorer focused on one composite. |
| [`/pbg-study <subcmd> …`](../skills/pbg-study/SKILL.md) | Full CRUD for **Studies** — baseline composites, variants, interventions, runs, behavior tests, follow-up proposals. Organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide). |
| [`/pbg-investigation <subcmd> …`](../skills/pbg-investigation/SKILL.md) | Manage **Investigations** — named collections of Studies grouped under a shared research question, with a cross-study dependency DAG. |
| [`/pbg-viz <study> <viz-name> '<description>'`](../skills/pbg-viz/SKILL.md) | Generate a `Visualization` subclass from a natural-language description and attach it to a Study. |
| [`/pbg-report [model\|--all]`](../skills/pbg-report/SKILL.md) | Regenerate `reports/index.html` after manual state changes. |
| [`/pbg-navigate <ac-gaps\|source\|finding-by-observable\|dag> …`](../skills/pbg-navigate/SKILL.md) | **Read-only** query of the workspace linkage index (SP4a) — the AC→study gating matrix + unlinked-AC gaps, source↔study, finding-by-observable, study-DAG. Pure deterministic derive (`linkage_index` / `/api/linkage-index`), no writes, no AI. |

For the read/write surface each skill touches (which API endpoints, which on-disk files), see the [Skill ↔ concept map](concepts/vivarium-workbench-model.md#skill--concept-map).

> Also shipped: `/pbg-init`, a one-shot machine-setup installer that symlinks the skills into `~/.claude/skills/`. Not part of the workflow surface above. And `/pbg-suggest <id>`, an internal callback the dashboard's "Suggest" button asks the user to paste — kept registered so the callback works, but not part of the user-facing catalog.

## Migration from v0.8

The v0.8 catalog had 17 user-invocable skills. v0.9 cuts that to 12
without losing any capability — repetitive trios are merged behind one
front door, and prototyping flags fold into the canonical commands.

| v0.8 skill | v0.9 equivalent |
|---|---|
| `/pbg-wrapper <tool>` | `/pbg-expert --lightweight <tool>` |
| `/pbg-composer <name> <tools…>` | `/pbg-expert --lightweight <name> <tools…>` |
| `/pbg-list` | `/pbg-catalog list` (or just `/pbg-catalog`) |
| `/pbg-install <pkg>` | `/pbg-catalog install <pkg>` |
| `/pbg-uninstall <pkg>` | `/pbg-catalog uninstall <pkg>` |
| `/pbg-package <repo>` | `python scripts/audit-pbg-repo.py <repo>` (maintainer-only) |

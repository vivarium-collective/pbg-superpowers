# Skills catalog

16 user-facing skills (plus `/viva-init` machine setup and one internal dashboard callback). Each entry links to the skill's `SKILL.md` for the full contract (front-matter, args, side effects).

## Wrap & compose

| Skill | What it does |
|---|---|
| [`/viva-expert <tool>`](../skills/viva-expert/SKILL.md) | Wrap a simulator as a Process — full sibling `pbg-<tool>/` repo with Process class, tests, README, HTML report, and a local commit. **Bridges the REAL tool by default** (keeps trying even when the build is hard); never silently downgrades. The canonical wrap. |
| [`/viva-expert <name> <tools…>`](../skills/viva-expert/SKILL.md) | Compose two or more wrapped simulators into a sibling `pbg-<name>-composite/` repo with HTML report and a local commit. |
| [`/viva-expert --lightweight <tool>`](../skills/viva-expert/SKILL.md#lightweight-mode) | Lightweight in-workspace wrap: writes `pbg_<slug>/processes/<tool>.py` + a test. Still a **real bridge** (lazy-imports + drives the genuine tool); only the repo scaffolding is dropped. No sibling repo, no report. (Alias: `--in-workspace`. Replaces v0.8 `/pbg-wrapper`.) |
| [`/viva-expert --lightweight <name> <tools…>`](../skills/viva-expert/SKILL.md#lightweight-mode) | Lightweight in-workspace composite: writes `pbg_<slug>/composites/<name>.py` + a test. (Replaces v0.8 `/pbg-composer`.) |
| [`/viva-expert --reproduce <tool>`](../skills/viva-expert/SKILL.md#reproduction-mode) | Opt-in: clean-room reimplement the tool's published algorithm as a labeled `<Tool>ReproductionProcess` (for when the real tool genuinely can't run here). Not the default. |
| [`/viva-expert --mock <tool>`](../skills/viva-expert/SKILL.md#mock-mode) | Opt-in: emit a non-functional `<Tool>MockProcess` placeholder (real ports, inert `update()`) for scaffolding/wiring only. Never a fallback for a hard build. Alias `--stub`. |

## Workspace lifecycle & dashboard

| Skill | What it does |
|---|---|
| [`/viva-workspace <name>`](../skills/viva-workspace/SKILL.md) | Scaffold a fresh workspace — three modes: upstream-branch (clone an upstream model repo and create a workspace branch), standalone (clone `pbg-template`), or in-place (promote an existing checkout). |
| [`/viva-workbench [start\|stop\|status\|open\|restart]`](../skills/viva-workbench/SKILL.md) | Start/stop/open the interactive vivarium-workbench (the side-rail-tabbed UI) and use its **session-per-tab** model — one workspace per browser tab. The single server every Studies skill depends on; it also serves the study reports. (Renamed from the former `/pbg-dashboard`.) |
| [`/viva-status`](../skills/viva-status/SKILL.md) | Print workspace health: is this a workspace? server up? recent activity? Probes the running workbench for server liveness. |

## Catalog & registry

| Skill | What it does |
|---|---|
| [`/viva-catalog [list]`](../skills/viva-catalog/SKILL.md) | Browse the workspace catalog — composites, studies, registry. Default subcommand when no args. (Replaces v0.8 `/pbg-list`.) |
| [`/viva-catalog install <pkg>`](../skills/viva-catalog/SKILL.md#install) | Add a curated `pbg-*` package, install it, refresh the workspace catalog. (Replaces v0.8 `/pbg-install`.) |
| [`/viva-catalog uninstall <pkg>`](../skills/viva-catalog/SKILL.md#uninstall) | Remove an installed `pbg-*` package. (Replaces v0.8 `/pbg-uninstall`.) |

Maintainer-only: to audit an external `pbg-*` repo for discovery- and
packaging-convention compliance, run `python scripts/audit-pbg-repo.py <repo>`
from a pbg-superpowers checkout. (Replaces the v0.8 `/pbg-package` skill.)

## Provenance & citations

| Skill | What it does |
|---|---|
| [`/viva-cite-bands <study-slug>`](../skills/viva-cite-bands/SKILL.md) | Guided band-provenance extraction (spine stage #3b) — surface candidate evidence from expert PDFs for uncited acceptance bands, then write structured `cites`/`calibration_anchor` into `study.yaml` via a deterministic comment-preserving helper. |
| [`/viva-biology-forward <study-slug>`](../skills/viva-biology-forward/SKILL.md) | Biology-forward results authoring (spine stage #5) — run `populate_finding_observations` to fill quantitative slots (`evidence.observed`, `expected.range`, `divergence_factor`) from `computed_outcomes`, then guide the agent to author the mechanism prose (`statement`/`summary`/`explanation`/`status`) over that scaffold. |

## Run, explore, study

| Skill | What it does |
|---|---|
| [`/viva-run <composite-id> [--steps N]`](../skills/viva-run/SKILL.md) | Run a composite directly (no Study attached). |
| [`/viva-study <subcmd> …`](../skills/viva-study/SKILL.md) | Full CRUD for **Studies** — baseline composites, variants, interventions, runs, behavior tests, follow-up proposals. Organized by lifecycle phase (Design → Build → Simulate → Evaluate → Decide). |
| [`/viva-tests <author\|enrich\|run> <study> …`](../skills/viva-tests/SKILL.md) | Author/enrich/run a study's **graded Tests** — the report cards that compile a run into a pass/fail verdict AND a signed `margin` (distance-to-pass) + a cross-iteration diff, the feedback signal for agent-driven model building. Uses `viva_superpowers.check()`/`TestBuilder`; bands over magic numbers. |
| [`/viva-audit-tests <study-slug>`](../skills/viva-audit-tests/SKILL.md) | Audit whether a study's `behavior_tests[]` are SUFFICIENT (discriminating, covering the question, independent, with a discriminating control) BEFORE they are pre-registered/locked — the AUDIT gate of the agentic model-building loop. Uses `viva_superpowers.test_audit.build_audit_report`/`audit_gate` plus AI reasoning (null-model plausibility, semantic coverage). |
| [`/viva-investigation <subcmd> …`](../skills/viva-investigation/SKILL.md) | Manage **Investigations** — named collections of Studies grouped under a shared research question, with a cross-study dependency DAG. |
| [`/viva-harden-investigation [slug]`](../skills/viva-harden-investigation/SKILL.md) | Make an existing **Investigation** rigorous — verify canonical source first, triage to the single load-bearing claim↔evidence gap, classify the hardening mode, root-cause failing report-card gates, and resolve open decisions. |
| [`/viva-viz <study> <viz-name> '<description>'`](../skills/viva-viz/SKILL.md) | Generate a `Visualization` subclass from a natural-language description and attach it to a Study. |
| [`/viva-report [model\|--all]`](../skills/viva-report/SKILL.md) | Regenerate `reports/index.html` after manual state changes. |
| [`/viva-navigate <ac-gaps\|source\|finding-by-observable\|dag> …`](../skills/viva-navigate/SKILL.md) | **Read-only** query of the workspace linkage index (SP4a) — the AC→study gating matrix + unlinked-AC gaps, source↔study, finding-by-observable, study-DAG. Pure deterministic derive (`linkage_index` / `/api/linkage-index`), no writes, no AI. |

For the read/write surface each skill touches (which API endpoints, which on-disk files), see the [Skill ↔ concept map](concepts/vivarium-workbench-model.md#skill--concept-map).

> Also shipped: `/viva-init`, a one-shot machine-setup installer that symlinks the skills into `~/.claude/skills/`. Not part of the workflow surface above. And `/viva-suggest <id>`, an internal callback the dashboard's "Suggest" button asks the user to paste — kept registered so the callback works, but not part of the user-facing catalog.

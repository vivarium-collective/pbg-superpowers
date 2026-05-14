---
name: pbg-report
description: Regenerate the workspace dashboard and per-model reports. Pulls workspace.yaml, decisions log, and (per model) the live process-bigraph registry; renders to <workspace>/reports/index.html and models/<model>/reports/index.html. Idempotent.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [model-name | --all]
---

# pbg-report

Transversal skill (no stage). Called by other stage skills at end-of-stage and runnable manually anytime to refresh the dashboards.

## What it produces

- `<workspace>/reports/index.html` — workspace dashboard: process registry, type registry, recent decisions, browsable composite document

The file includes CSS + JS in `<reports>/assets/` (copied from the plugin's `templates/_assets/` and, if present, `server/client.js` for the live-dashboard mode).

## Operation

- **No args** → regenerate workspace report.

Internally:

```bash
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'))"
```

The skill reads `workspace.yaml` for the workspace slug, then builds `pbg_doc` from `pbg_<slug>.document.build_document()` if available; falls back to an empty dict.

## Idempotency

`/pbg-report` produces deterministic output given the same inputs. The `--today` argument can be passed through for byte-stable CI runs:

```bash
python -c "..." # render_*_report(..., today='2026-05-09')
```

## Safety

- Never modifies `workspace.yaml`, `decisions.yaml`, or any other persistent state — read-only consumer.
- Refuses to run if `workspace.yaml` is malformed (lint-workspace.py disagreement is fatal).
- Per-model rendering catches `build_core()` failures, logs them, and emits a stub deep-dive panel rather than crashing the entire report.

## When stage skills invoke this

Every stage skill that completes a stage should invoke `/pbg-report` (or its programmatic equivalent) as part of step 8 of the spec §7 lifecycle. The dashboards are then up-to-date for the next stage.

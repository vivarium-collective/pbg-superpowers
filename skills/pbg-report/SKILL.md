---
name: pbg-report
description: Regenerate the workspace dashboard and per-model reports. Pulls workspace.yaml, phase frontmatters, decisions log, and (per model) the live process-bigraph registry; renders to <workspace>/reports/index.html and models/<model>/reports/index.html. Idempotent.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [model-name | --all]
---

# pbg-report

Transversal skill (no stage). Called by other stage skills at end-of-stage and runnable manually anytime to refresh the dashboards.

## What it produces

- `<workspace>/reports/index.html` — workspace dashboard: model registry, recent decisions, links into per-model reports
- `<workspace>/models/<model>/reports/index.html` — per-model deep-dive: phase tracker, process registry, type registry, per-phase deep-dive sections, browsable composite document

Both files include CSS + JS in `<reports>/assets/` (copied from the plugin's `templates/_assets/` and, if present, `server/client.js` for the live-dashboard mode).

## Operation

- **No args** → regenerate workspace report only.
- **`/pbg-report <model>`** → regenerate workspace report + that model's report.
- **`/pbg-report --all`** → regenerate workspace report + every registered model's report.

Internally:

```bash
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'))"
```

For each model:

```bash
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_model_report; \
           from pbg_superpowers.core_introspection import registry_snapshot; \
           from pbg_<slug>.core import build_core; \
           reg = registry_snapshot(build_core()); \
           render_model_report(Path('.'), '<model-name>', reg)"
```

The skill auto-detects each model's slug from `workspace.yaml.models.<name>.submodule_path`. Builds `pbg_doc` from `pbg_<slug>.document.build_document()` if available; falls back to an empty dict.

## Idempotency

`/pbg-report` produces deterministic output given the same inputs. The `--today` argument can be passed through for byte-stable CI runs:

```bash
python -c "..." # render_*_report(..., today='2026-05-09')
```

## Safety

- Never modifies `workspace.yaml`, `phases/*.md`, `decisions.yaml`, or any other persistent state — read-only consumer.
- Refuses to run if `workspace.yaml` is malformed (lint-workspace.py disagreement is fatal).
- Per-model rendering catches `build_core()` failures, logs them, and emits a stub deep-dive panel rather than crashing the entire report.

## When stage skills invoke this

Every stage skill that completes a stage should invoke `/pbg-report` (or its programmatic equivalent) as part of step 8 of the spec §7 lifecycle. The dashboards are then up-to-date for the next stage.

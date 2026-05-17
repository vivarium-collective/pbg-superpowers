---
name: pbg-report
description: Regenerate the workspace dashboard and per-model reports. Pulls workspace.yaml, decisions log, and (per model) the live process-bigraph registry; renders to <workspace>/reports/index.html and models/<model>/reports/index.html. Pre-publication lint runs first — blocking errors refuse to render unless --force logs an override. Idempotent.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [model-name | --all | --lint | --force]
---

# pbg-report

Transversal skill (no stage). Called by other stage skills at end-of-stage and runnable manually anytime to refresh the dashboards.

## What it produces

- `<workspace>/reports/index.html` — workspace dashboard: process registry, type registry, recent decisions, browsable composite document

The file includes CSS + JS in `<reports>/assets/` (copied from the plugin's `templates/_assets/` and, if present, `server/client.js` for the live-dashboard mode).

## Operation

- **No args** → run the report linter, then regenerate the workspace report.
- **`--lint`** → run the linter only; do NOT render. Useful in CI / pre-PR.
- **`--force`** → if blocking lint errors exist, log them to `.pbg/report-lint-overrides.json` and render anyway. Required to bypass blocked publication.

Internally:

```bash
# Lint-only (Pass B):
python -m pbg_superpowers.report_linter --ws .

# Standard render (lint first; refuse on blocking errors):
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'))"

# Forced render with auto-logged overrides:
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'), force=True)"
```

The skill reads `workspace.yaml` for the workspace slug, then builds `pbg_doc` from `pbg_<slug>.document.build_document()` if available; falls back to an empty dict.

## Pre-publication linter (Pass B)

Before rendering, `/pbg-report` runs `pbg_superpowers.report_linter.lint_workspace_report()` over every study under `<ws>/studies/` and `<ws>/investigations/`. Checks:

- **incomplete_summaries** (error) — `evaluation_status: evaluated` but `conclusion_logic` is empty.
- **status_contradictions** (error) — gate/evaluation/sim/impl/review combinations that cannot logically co-exist (e.g. `gate_status: passed` with `evaluation_status: failed_evaluation`).
- **missing_provenance** (error) — a finding marked run-derived (`evaluation_status: evaluated` or `evidence.from_run: true`) with empty `provenance.run_ids`.
- **unresolved_placeholders** (error) — any string field containing `TBD`, `TODO`, `XXX`, `[fill in]`, or `<insert>` (case-insensitive). Slug fields like `name`/`id`/`composite` are excluded.
- **duplicate_modal_phrases** (warning) — pairs of `behavior_tests[].description` that are ≥90% character-identical (copy-paste residue).
- **truncated_takeaways** (error) — `conclusion_logic.if_pass`, `if_fail`, `*.biological_validation`, `*.block_downstream` that end mid-sentence or are <20 chars.

Only **error**-level findings block publication; **warning** and **info** are surfaced but pass through.

### Override file format

`<ws>/.pbg/report-lint-overrides.json`:

```json
{
  "schema_version": 1,
  "overrides": [
    {
      "key": "<check>:<study-slug>:<sha256[:12]>",
      "added_at": "2026-05-17T15:14:00",
      "reason": "force-published via /pbg-report --force",
      "check": "incomplete_summaries",
      "study_slug": "dnaa-02-autorepression",
      "field_path": "conclusion_logic",
      "message": "...verbatim message at time of override..."
    }
  ]
}
```

`--force` is idempotent: re-running it on the same blocking finding does not double-append. To re-block a previously overridden finding, delete its `overrides[]` entry by hand.

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

# Run → Visualization Provenance & Freshness — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming), ready for implementation plan
**Repos:** `pbg-superpowers` (runners, backfill, refresh-viz skill, linter) + `vivarium-workbench` (freshness read, study-card badges, report)

## Problem

When a study (or whole investigation) is rerun, its visualizations often do **not**
get updated: bespoke chart scripts (`render_*.py` → `charts/*.svg`) carry no record
of which run produced them, reruns update `runs.db` without regenerating those
charts, and the run↔study link + "which run is latest" are inferred loosely. Result:
stale charts silently keep showing, and reviewers can't tell which figures reflect
the latest run.

## Goal

A rerun never leaves stale charts silently showing. Every chart records which run
produced it; the study has an authoritative "latest run"; the dashboard, report, and
linter all surface fresh vs stale vs untracked; registered charts auto-regenerate on
rerun, unregistered ones are flagged for manual refresh.

## Locked decisions (from brainstorming)

1. **Behavior:** *Both* — always detect/flag staleness; auto-regenerate charts that
   are registered as re-runnable; flag + prompt for the rest.
2. **Provenance model:** `study.yaml visualizations[]` declares the render command;
   a per-chart `<chart>.meta.json` sidecar records the source run. (Not runs.db
   artifacts; not a separate lock file.)
3. **Latest run:** `studies/<slug>/runs.db` is authoritative — every runner registers
   a row; backfill auto-registers discovered parquet/zarr; latest = newest finished row.
4. **One shipment** (not phased).
5. **Error handling:** a failed render keeps the chart's old meta (stays flagged
   stale), reports the error, and never aborts the rerun. Locked/missing `runs.db`
   degrades gracefully (existing WAL-safe read).
6. **Linter level:** the new staleness check is **warning** by default, **error**
   under `--strict`.

This extends existing infra — `runs_meta` (+ its `generation_id`), `visualizations[]`,
`.meta.json` sidecars, `backfill_runs`, and the `figure_stale_vs_run` linter — rather
than greenfield.

## Architecture

### A. Run registry — `runs.db` authoritative

- Every runner (`run-baseline`, `run-variant`, `run-script`) writes/updates a
  `runs_meta` row with: `run_id, started_at, finished_at, emitter_path,
  generation_id, status`. (`emitter_path` is new: the parquet/zarr/sqlite store the
  run wrote, so bespoke multi-gen runners are linked.)
- `backfill_runs` is extended: on dashboard read, auto-register any discovered
  parquet/zarr run directory under the study that is not already a `runs_meta` row
  (so a bespoke runner that didn't self-register still appears, with `finished_at`
  from the store's newest partition mtime).
- New helper `latest_run(slug) -> dict | None`: the newest `finished_at` row (falls
  back to `started_at`). This is the single staleness reference point.

### B. Visualization registry — `visualizations[]` + sidecar

`study.yaml visualizations[]` entry schema (additive; existing entries still valid):

```yaml
visualizations:
  - name: dnaa3_binding_analysis
    chart: charts/dnaa3_binding_analysis.svg     # output path (relative to study dir)
    render: "python scripts/render_dnaa3_binding_analysis.py --out {chart}"   # re-runnable command
    # optional: source_run: <run_id>             # pin to a specific run; default = latest_run
```

At render time (whether via `refresh-viz` or the bespoke script when run through it),
the renderer writes/updates `<chart>.meta.json`:

```json
{
  "source_run_id": "dnaa3-seed1-8gen",
  "generation_id": "...",
  "rendered_at": 1717800000,
  "command": "python scripts/render_dnaa3_binding_analysis.py --out charts/dnaa3_binding_analysis.svg",
  "content_hash": "sha256:..."
}
```

`visualizations[]` is the manifest of *what should show*. A `charts/*.svg` file with
no matching entry is **untracked / orphan** (flagged, not shown as authoritative).

### C. Freshness

Pure function `chart_freshness(study_dir, entry, latest)` →
`"fresh" | "stale" | "untracked" | "unrendered"`:

- **fresh** — `meta.source_run_id == latest.run_id` AND `meta.rendered_at >= latest.finished_at`.
- **stale** — meta exists but `source_run_id != latest.run_id` (or rendered before the run finished).
- **unrendered** — entry declared but no chart file / no meta yet.
- **untracked** — a `charts/*.svg` with no `visualizations[]` entry.

Surfaced in three places, all reading this one function:
1. **Dashboard study card** — per-chart badge in the Visualisations section:
   ✓ *latest run* / ⚠ *stale: from run X* / ❓ *untracked* / ◌ *not yet rendered*,
   plus a "Refresh" affordance.
2. **Generated report** — same badge inline beside each figure.
3. **`report_linter`** — new check `viz_stale_vs_latest_run` (warning; error under
   `--strict`) for any stale/untracked chart in an evaluated study. The existing
   `figure_stale_vs_run` is folded into / superseded by this.

### D. Regeneration — `refresh-viz`

- `/pbg-study refresh-viz <study>`: for each `visualizations[]` entry with a `render:`
  command, re-run it against `latest_run(slug)` (substituting `{chart}`, and exposing
  the run's `emitter_path` via an env var, e.g. `PBG_RUN_DIR`), then re-stamp the
  chart's `.meta.json`. Entries without a command, and untracked `charts/*.svg`, are
  reported as "needs manual refresh: <path>".
- `/pbg-investigation refresh-viz <inv> [--studies a,b]`: orchestrates the above over
  member studies.
- **Auto-on-rerun:** `run-baseline` / `run-variant` / `run-script` call `refresh-viz`
  for that study at the end (skippable with `--no-refresh-viz`), so a rerun self-heals
  its registered charts.
- Render-error tolerant (mirrors `preview-viz`): a command that fails leaves the old
  chart + meta in place (still flagged stale), records the error in the response, and
  does not abort the run or the other charts.

## Data flow

```
rerun study
  └─ runner writes runs_meta row  ───────────────►  latest_run(slug) = new run
        └─ (auto) refresh-viz
              └─ for each visualizations[] entry with render:
                    run command against latest run  ──►  chart.svg + chart.meta.json(source_run_id=latest)
              └─ entries w/o command + orphan charts/*.svg  ──►  reported "needs manual refresh"
  └─ dashboard / report / linter read chart_freshness(...)  ──►  ✓ fresh (all registered) ; ⚠ the rest flagged
```

## Components & files (one shipment)

**pbg-superpowers**
- `pbg_superpowers/composite_runs.py` (or runner modules): add `emitter_path` to
  `runs_meta`; write the row from each runner; `latest_run(slug)` helper.
- `pbg_superpowers/backfill_runs.py`: discover + register parquet/zarr run dirs.
- `pbg_superpowers/viz_freshness.py` (new): `chart_freshness()`, meta read/stamp,
  manifest-vs-charts diff. Pure, unit-tested.
- `pbg_superpowers/report_linter.py`: `viz_stale_vs_latest_run` check (warning;
  error under `--strict`); retire/fold `figure_stale_vs_run`.
- `skills/pbg-study/SKILL.md`: `refresh-viz` subcommand + `visualizations[].render`
  convention + `--no-refresh-viz` on the run-* verbs.
- `skills/pbg-investigation/SKILL.md`: `refresh-viz`.
- `docs/concepts/vivarium-workbench-model.md`: document `render:` + `.meta.json`
  provenance + freshness states.

**vivarium-workbench**
- `lib/viz_freshness.py`: vendored mirror of the freshness function (drift-guard
  test, same pattern as `workspace_paths`).
- `server.py`: a `/api/study-viz-render`/`refresh-viz` endpoint (or extend existing)
  that runs declared `render:` commands; freshness fields in the study/charts API.
- `static/walkthrough.js`: per-chart freshness badge + "Refresh" affordance in the
  Visualisations section (live card + generated report).

## Out of scope (YAGNI)

- Cross-study / cross-investigation viz dependency graphs.
- Re-running the *simulation* automatically when inputs change (this design refreshes
  *visualizations* against the latest run; it does not decide when to re-simulate).
- Versioned chart history / diffing beyond the single `content_hash`.

## Testing

- **Unit (pbg-superpowers):** `latest_run` picks newest finished row; `chart_freshness`
  returns fresh/stale/untracked/unrendered correctly; meta stamp round-trips;
  `backfill_runs` discovers + registers a parquet/zarr dir; `refresh-viz` re-runs a
  command + restamps; a failing command leaves old meta + reports error.
- **Linter:** `viz_stale_vs_latest_run` fires (warning) on `source_run_id != latest`;
  becomes error under `--strict`; clean when all fresh.
- **Dashboard:** charts API returns freshness states; study-card render shows the
  right badge per state (render test).
- **Back-compat:** a study with legacy `visualizations[]` (no `render:`) + existing
  charts lints as "untracked/needs manual refresh", not a crash.

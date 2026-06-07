# Investigation-scoped Inputs + Global Tagged/Multi-emitter SimulationsDB — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming), ready for implementation plan
**Repos:** `pbg-superpowers` (paths, schema, run-sweep helper, migration, skills) + `vivarium-dashboard` (sidebar, Inputs page, SimulationsDB page)

## Problem

Two sidebar pages are global but are really **investigation-dependent**:

1. **Inputs** (datasets + references + expert docs) is a repo-level shared pool in the
   top rail, yet its content is meaningful only in the context of the loaded
   investigation.
2. **SimulationsDB** lists runs from per-study `runs.db` (SQLite) with no clear
   investigation/study tagging, and it does **not** surface Parquet (`ParquetEmitter`)
   or XArray (`XArrayEmitter`/zarr) results that are saved on disk — only SQLite.

Separately, the menu lacked investigation lifecycle control and branch-aware
selection — both shipped already (vivarium-dashboard #166); this spec covers only
the two redesign pieces (#3 Inputs, #4 SimulationsDB).

## Goal

Inputs become **owned by the investigation** and live in the per-investigation
sidebar section. SimulationsDB stays one **global** table but tags every run by
investigation/study, shows its **emitter type**, defaults to the loaded
investigation, and surfaces SQLite + Parquet + XArray runs.

## Locked decisions (from brainstorming)

1. **Inputs: per-investigation ownership.** Each investigation owns its inputs under
   `investigations/<slug>/inputs/`; `investigation.yaml` declares them. No global
   Inputs page. Cross-investigation references are duplicated or symlinked.
2. **This reverses** the investigation-centric-restructure decision that kept
   `references/`+`datasets/` repo-level — accepted, with a one-time migration pass.
3. **SimulationsDB: global table, current-investigation default.** All runs, columns
   investigation · study · run · emitter type · time · status; defaults to filtering
   on the loaded investigation with a toggle to "all"; filters by study/emitter.
4. **Multi-emitter discovery via the run registry**, not blind FS scan: per-study
   `runs.db` `runs_meta` (+ `emitter_path`, merged in #104) + `backfill_study_runs`
   to auto-register on-disk Parquet/XArray stores.
5. **Parquet/XArray rows** link to their store + open in the existing zarr/viz path —
   **no inline data preview** in SimulationsDB (YAGNI).

## Part 1 — Investigation-scoped Inputs

### On-disk
```
investigations/<slug>/
  investigation.yaml          # gains an `inputs:` block (below)
  inputs/
    datasets/                 # data files the investigation validates against
    references/papers.bib     # per-investigation bibliography (+ notes/)
```
`investigation.yaml` `inputs:` block (all keys optional):
```yaml
inputs:
  datasets:
    - name: beulig-2018-batch
      path: inputs/datasets/beulig_2018.csv
      supports_claims: ["acetate cycle time ~136 min"]
  references: [Boesen2024, Si2017]      # bib keys present in inputs/references/papers.bib
  expert_docs: [inputs/notes/rashmi-2026-05-31.md]
```

### Sidebar
- Remove the global top-rail **Inputs** item (`index.html.j2:317-326`).
- Add an **Inputs** entry to the per-investigation lower section (the rail group that
  shows the loaded investigation's Studies). It is visible only when an investigation
  is loaded and shows *that* investigation's inputs.

### Server
- `WorkspacePaths.inputs_dir(slug) -> investigations/<slug>/inputs` (pbg-superpowers +
  vendored dashboard copy, drift-guarded like `study_dir`).
- The inputs endpoint becomes investigation-scoped: `GET /api/iset/<slug>/inputs`
  returns `{datasets, references, expert_docs}` resolved from
  `investigations/<slug>/inputs/` + `investigation.yaml.inputs`. The old global
  `page-workspace-inputs` route is removed (or 410s with a pointer).

### Migration (the one decision needing the author)
- `pbg-migrate-inputs` (new CLI, idempotent): for each existing repo-level
  `datasets/` entry and `references/papers.bib` key, assign it to an investigation.
  Default assignment heuristic: an item used by exactly one investigation's studies →
  that investigation; ambiguous/shared items → reported for manual assignment (printed
  list; not moved). Moves via `git mv` (history preserved); writes the `inputs:` block.
- Until migrated, the resolver falls back to repo-level `references/`+`datasets/` so
  nothing 404s mid-migration (transitional read-through, logged).

## Part 2 — Global tagged/multi-emitter SimulationsDB

### Server — `list_all_runs(ws_root)` (pbg-superpowers, vendored to dashboard)
For every study dir (`iter_study_dirs`):
- `backfill_study_runs(study_dir, spec_id)` first (register on-disk Parquet/XArray).
- Read `runs_meta` rows; for each emit:
  `{investigation: study_owner(slug), study: slug, run_id, started_at, completed_at,
    status, emitter_path, emitter_type}`.
- `emitter_type` derivation (pure helper `emitter_type_of(emitter_path)`):
  `*.zarr` (or a dir containing `.zarr`) → `XArray`; `*.parquet` (or a dir of
  `*.parquet`) → `Parquet`; ends `.db`/`runs.db`/empty → `SQLite`.
- Endpoint `GET /api/simulations` returns the flat list; sorted newest-first.

### SPA — SimulationsDB page
- Render a table: **investigation · study · run · emitter · time · status**, with an
  emitter-type pill (SQLite/Parquet/XArray, distinct colors).
- **Default filter = the loaded (current-branch) investigation**; a toggle switches to
  **All**; dropdown filters for study + emitter type.
- A Parquet/XArray row's run links to its `emitter_path` store and, where a zarr viz
  exists (the existing `_zarr_store_for_sim` path), an "open viz" affordance. No inline
  table/array preview.

## Components & files

**pbg-superpowers**
- `pbg_superpowers/workspace_paths.py`: `inputs_dir(slug)`.
- `pbg_superpowers/run_registry.py` (or a new `runs_index.py`): `list_all_runs(ws_root)`
  + `emitter_type_of(path)` (pure, unit-tested).
- `pbg_superpowers/migrate_inputs.py` (new): `pbg-migrate-inputs`.
- `skills/pbg-investigation/SKILL.md`: document the `inputs:` block + inputs-add verbs.
- `docs/concepts/vivarium-dashboard-model.md`: inputs ownership + SimDB tagging.

**vivarium-dashboard**
- `lib/workspace_paths.py` (vendored `inputs_dir`), `lib/runs_index.py` (vendored
  `list_all_runs`/`emitter_type_of`), drift-guard tests.
- `server.py`: `GET /api/iset/<slug>/inputs`; `GET /api/simulations`; remove global
  inputs route.
- `static/walkthrough.js` + `templates/index.html.j2`: move Inputs into the
  per-investigation rail section; rebuild the SimulationsDB page as the tagged table
  with current-default filter + emitter pills.

## Out of scope (YAGNI)
- Inline data/array preview of Parquet/XArray inside SimulationsDB (link + existing viz only).
- Cross-investigation shared-pool inputs (ownership is exclusive; share via symlink).
- Re-running / deleting runs from SimulationsDB (read-only listing).

## Phasing (independent, buildable in order)
- **Phase 1 — Inputs:** `inputs_dir`, the `inputs:` schema, scoped endpoint, sidebar
  move, `pbg-migrate-inputs`, transitional read-through.
- **Phase 2 — SimulationsDB:** `list_all_runs`/`emitter_type_of`, `/api/simulations`,
  the tagged table + current-default filter + emitter pills.

## Testing
- **Inputs:** `inputs_dir` resolution; scoped endpoint returns the investigation's
  datasets/refs; migration assigns single-use items + reports ambiguous ones;
  transitional read-through when un-migrated.
- **SimDB:** `emitter_type_of` (parquet/zarr/sqlite/dir cases); `list_all_runs` tags
  investigation/study + includes backfilled Parquet/XArray; endpoint shape; SPA
  current-default filter + "All" toggle (render test).
- **Drift guards:** vendored `inputs_dir`/`runs_index` match the pbg-superpowers canonical.

# Investigation-scoped Inputs + Global Tagged/Multi-emitter SimulationsDB — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming), ready for implementation plan
**Repos:** `pbg-superpowers` (paths, schema, run-sweep helper, migration, skills) + `vivarium-workbench` (sidebar, Inputs page, SimulationsDB page)

## Problem

Two sidebar pages are global but are really **investigation-dependent**:

1. **Inputs** (datasets + references + expert docs) is a repo-level shared pool in the
   top rail, yet its content is meaningful only in the context of the loaded
   investigation.
2. **SimulationsDB** lists runs from per-study `runs.db` (SQLite) with no clear
   investigation/study tagging, and it does **not** surface Parquet (`ParquetEmitter`)
   or XArray (`XArrayEmitter`/zarr) results that are saved on disk — only SQLite.

Separately, the menu lacked investigation lifecycle control and branch-aware
selection — both shipped already (vivarium-workbench #166); this spec covers only
the two redesign pieces (#3 Inputs, #4 SimulationsDB).

## Goal

Investigation-specific Inputs become **owned by the investigation** (per-investigation
sidebar); a **global Inputs tab is kept** for repo-wide/shared data sources. SimulationsDB stays one **global** table but tags every run by
investigation/study, shows its **emitter type**, defaults to the loaded
investigation, and surfaces SQLite + Parquet + XArray runs.

## Locked decisions (from brainstorming)

1. **Inputs: HYBRID (global repo-wide + per-investigation).** A global **Inputs** tab
   REMAINS in the top rail for **repo-wide / shared data sources** — imported source
   packages (e.g. v2ecoli's `ecoli-sources` TSVs) and datasets/refs not tied to any
   investigation. **Investigation-specific** datasets/references are owned
   per-investigation under `investigations/<slug>/inputs/` and shown in the
   per-investigation sidebar. An input is either *global* (repo-wide) or
   *investigation-owned*. (Revised 2026-06-07 from pure per-investigation ownership.)
2. **Repo-wide sources stay repo-level** (the global tab keeps the restructure's pool);
   only investigation-specific inputs move into the investigation (migration pass).
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

### Inputs tab — investigation-first (parallel to SimulationsDB)
The global top-rail **Inputs** tab shows TWO sections, **current-investigation-first**
(the same pattern as SimulationsDB):
1. **This investigation's inputs** (top) — the loaded investigation's
   datasets/references/expert-docs from `investigations/<slug>/inputs/` +
   `investigation.yaml.inputs`. (Revised 2026-06-07: surfaced in the global tab rather
   than a separate sidebar item.)
2. **Repo-wide data sources** (below) — imported source packages (e.g. `ecoli-sources`
   TSVs) + shared datasets/refs not owned by any investigation.
On-disk ownership is unchanged (investigation-specific under
`investigations/<slug>/inputs/`; repo-wide stays repo-level).

### Server
- `WorkspacePaths.inputs_dir(slug) -> investigations/<slug>/inputs` (pbg-superpowers +
  vendored dashboard copy, drift-guarded like `study_dir`).
- `GET /api/inputs` returns `{investigation: {datasets, references, expert_docs},
  global: {datasets, references, sources}, current: <slug>}` — the investigation block
  is the loaded investigation's owned inputs; `global` is repo-wide; `current` lets the
  SPA order investigation-first (parallel to `/api/simulations`).

### Migration (the one decision needing the author)
- `pbg-migrate-inputs` (new CLI, idempotent): assign each existing repo-level
  `datasets/` entry / `references/papers.bib` key. Heuristic: an item used by exactly
  one investigation's studies → that investigation; **imported source packages and
  multi-investigation / unused items → STAY global** (reported, not moved). Moves via
  `git mv` (history preserved); writes the `inputs:` block.
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
- `viva_superpowers/workspace_paths.py`: `inputs_dir(slug)`.
- `viva_superpowers/run_registry.py` (or a new `runs_index.py`): `list_all_runs(ws_root)`
  + `emitter_type_of(path)` (pure, unit-tested).
- `viva_superpowers/migrate_inputs.py` (new): `pbg-migrate-inputs`.
- `skills/pbg-investigation/SKILL.md`: document the `inputs:` block + inputs-add verbs.
- `docs/concepts/vivarium-workbench-model.md`: inputs ownership + SimDB tagging.

**vivarium-workbench**
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

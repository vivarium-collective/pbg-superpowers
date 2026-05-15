# vivarium-dashboard Data Model

The canonical concepts pbg-superpowers reads, writes, and orchestrates in a vivarium-dashboard workspace. This document is the source of truth for vocabulary, on-disk shape, and the API surface that maps each concept to skill commands.

> **Companion repo:** [vivarium-dashboard](https://github.com/vivarium-collective/vivarium-dashboard). pbg-superpowers requires its server to be running for any skill that mutates dashboard state.

## At a glance

```
Workspace
  ├── Composites (in pbg_<pkg>/composites/, discovered by the catalog)
  ├── Studies (in studies/<name>/study.yaml — v3)
  │     ├── Baseline      (list of composites, each {name, composite, params})
  │     ├── Variants      (list of perturbations, each {name, base_composite, parameter_overrides})
  │     ├── Interventions (list of text-described conditions, each {name, description})
  │     ├── Runs          (list of completed executions; per-baseline-entry or per-variant)
  │     └── Visualizations (list of named viz configs)
  └── Visualization classes / registry (workspace-wide)
```

## The concepts

### Workspace

A directory containing `workspace.yaml`, a `pbg_<package>/` Python package, and the dashboard's runtime state under `.pbg/server/`.

- **On disk:** `<workspace>/workspace.yaml` + `pbg_<pkg>/`.
- **In the dashboard:** the root container; everything else lives inside it.
- **Created by:** `/pbg-init`.

### Study

A self-contained research unit: question + baseline composite(s) + variants + interventions + runs + visualizations + conclusion.

- **On disk:** `<workspace>/studies/<name>/study.yaml` (schema_version 3). Legacy v2 specs live at `<workspace>/investigations/<name>/spec.yaml` and are migrated to v3 in-memory on read.
- **Identity:** the directory name (a slug like `study-monod_kinetics-096184`).
- **v3 shape:** `{schema_version: 3, name, objective, status, baseline: [...], variants: [...], interventions: [...], runs: [...], visualizations: [...], conclusion}`.
- **Created by:** `/pbg-study new`. **Managed by:** `/pbg-study`. **Listed by:** `/pbg-list`.

> "Study" is the canonical term. "Investigation" is the v2 name, retained only in on-disk legacy paths and accepted as a synonym in some API bodies (`investigation:` body key still works via `_study_name_from_body`).

### Baseline

A study's set of runnable composites — **one or more**. Each entry is a runnable composite document with optional parameter defaults.

- **Shape:** `[{name: <unique-in-study>, composite: <pkg.composites.x>, params: {...}}]` — a **non-empty list**.
- **Why a list:** a study can compare growth across multiple baseline composites side-by-side, not just variants of one.
- **API:** `POST /api/study-baseline-add`, `POST /api/study-baseline-remove`, `POST /api/study-run-baseline {study, composite?}`.
- **Skill:** `/pbg-study baseline-add`, `/pbg-study baseline-remove`, `/pbg-study run-baseline`.

### Variant

A single baseline composite + parameter overrides. Each variant names which composite it derives from via `base_composite`.

- **Shape:** `{name, base_composite: <baseline-entry-name>, parameter_overrides: {...}}`.
- **`base_composite` must reference an existing name in `baseline[]`** — validated server-side; removing a baseline entry that variants depend on returns 409.
- **Scope:** parameter overrides only. Initial-state editing and process/module swaps are deferred.
- **API:** `POST /api/study-variant-add`, `POST /api/study-variant-set-params`, `POST /api/study-variant-delete`, `POST /api/study-run-variant`.
- **Skill:** `/pbg-study variant-add`, `/pbg-study variant-set-params`, `/pbg-study variant-delete`, `/pbg-study run-variant`.

### Intervention

A standalone, text-described experimental condition. Fully separate from variants — no data link in this phase.

- **Shape:** `{name, description}` — `name` is a short slug; `description` is freeform text.
- **API:** `POST /api/study-intervention-add`, `POST /api/study-intervention-update`, `POST /api/study-intervention-delete`.
- **Skill:** `/pbg-study intervention-add`, `/pbg-study intervention-update`, `/pbg-study intervention-delete`.

### Run

A completed execution of a baseline composite or variant. The dashboard records run metadata; the actual simulation trace lives in `runs.db` (per study).

- **Shape:** `{run_id, variant: <name|null>, composite: <baseline-entry-name>, label, status, n_steps}`. `variant: null` indicates a baseline run.
- **API:** `POST /api/study-run-baseline {study, composite?}`, `POST /api/study-run-variant {study, variant}`, `POST /api/study-run-delete`, `POST /api/study-runs-clear`, `POST /api/study-comparison-add {study, run_ids}`.
- **Skill:** `/pbg-study run-baseline`, `/pbg-study run-variant`.

### Visualization

A named visualization config attached to a study. Renders run output to HTML.

- **Shape:** `{name, address, config}`. `address` is a dotted reference to a `Visualization` (a `Step` subclass — see `docs/conventions/visualizations.md`).
- **API:** `POST /api/study-viz-add` (alias `/api/investigation-add-viz`), `POST /api/study-viz-render`.
- **Skill:** `/pbg-viz`.

## The dashboard server (read surface)

Skills that read dashboard state do so via these HTTP endpoints:

| Endpoint | Returns | Used by |
|---|---|---|
| `GET /api/investigations` | All studies with summary fields (`name, status, baseline_names, n_baseline, n_variants, n_interventions, n_runs, baseline_source, conclusions_excerpt`) | `/pbg-list` |
| `GET /api/workspace-manifest` | Composites, studies, registry, health | `/pbg-status`, `/pbg-list` |
| `GET /api/investigation-composites?investigation=<n>` | A study's baseline list as `[{name, source, params}]` | `/pbg-study`, UI |
| `GET /api/composite-resolve?id=<id>&overrides=<json>` | A composite's `{parameters, state, svg, kind, ...}` for param-form pre-fill | `/pbg-explore`, UI |
| `GET /api/composites` | Workspace catalog of discoverable composites | `/pbg-list` |

## The dashboard server (write surface)

| Endpoint | Body | Skill subcommand |
|---|---|---|
| `POST /api/study-set-objective` | `{study, text}` | `/pbg-study set-objective` |
| `POST /api/study-set-conclusion` | `{study, text}` | `/pbg-study set-conclusion` |
| `POST /api/study-baseline-add` | `{study, name, composite, params?}` | `/pbg-study baseline-add` |
| `POST /api/study-baseline-remove` | `{study, name}` | `/pbg-study baseline-remove` |
| `POST /api/study-run-baseline` | `{study, composite?, steps?}` | `/pbg-study run-baseline` |
| `POST /api/study-variant-add` | `{study, name, base_composite, parameter_overrides?}` | `/pbg-study variant-add` |
| `POST /api/study-variant-set-params` | `{study, variant, parameter_overrides}` | `/pbg-study variant-set-params` |
| `POST /api/study-variant-delete` | `{study, variant}` | `/pbg-study variant-delete` |
| `POST /api/study-run-variant` | `{study, variant, steps?}` | `/pbg-study run-variant` |
| `POST /api/study-intervention-add` | `{study, name, description?}` | `/pbg-study intervention-add` |
| `POST /api/study-intervention-update` | `{study, name, description}` | `/pbg-study intervention-update` |
| `POST /api/study-intervention-delete` | `{study, name}` | `/pbg-study intervention-delete` |
| `POST /api/study-viz-add` | `{study, name, address, config}` | `/pbg-viz` |
| `POST /api/composite-test-run` | `{id, steps, emit_paths?}` | `/pbg-run` |

## Skill ↔ concept map

| Skill | Reads | Writes | Notes |
|---|---|---|---|
| `/pbg-init` | — | Workspace | Scaffolds new workspace. |
| `/pbg-server` | `.pbg/server/server-info` | Starts/stops dashboard server. | Required precondition for every other dashboard-touching skill. |
| `/pbg-list` | Workspace, Composites, Studies | — | Read-only catalog. |
| `/pbg-status` | Workspace state | — | Server up? recent activity? |
| `/pbg-install` / `/pbg-uninstall` | Workspace | Workspace deps | Wraps `pip install` + workspace catalog. |
| `/pbg-package` | Workspace | Workspace | Scaffolds a new composite into `pbg_<pkg>/composites/`. |
| `/pbg-composer` | Composite catalog | Workspace composite file | Generates a composite spec from prompts. |
| `/pbg-wrapper` | External Process | Workspace composite file | Wraps an existing simulator as a Process. |
| `/pbg-expert` | — | — | Domain reference for biology + Process design. |
| `/pbg-suggest` | Workspace | — | Suggests next actions. |
| `/pbg-explore` | Composite | Dashboard view | Opens composite in dashboard. |
| `/pbg-run` | Composite | Run record | Runs a composite directly (no Study). |
| `/pbg-study` | Study | Study | **All Study CRUD + runs.** See subcommand table above. |
| `/pbg-viz` | Visualization | Visualization | Adds a viz to a study. |
| `/pbg-report` | Study | Report file | Renders study summary to markdown. |
| `/pbg-workspace` | Workspace | Workspace state | Workspace-level commands. |

## Migration notes

- **v2 → v3 on read:** `vivarium_dashboard.lib.spec_migration.migrate_v2_to_v3` runs automatically in `load_spec`. Skills never need to invoke it.
- **v2 endpoints still aliased:** `/api/investigation-add-viz`, `/api/investigation-render-viz`, and a few others remain as aliases of their `/api/study-*` v3 counterparts. New skill code should prefer the `study-` form.
- **Removed in v3:** `/api/study-set-baseline-params` (covered by `study-variant-set-params` + the new baseline-list shape); `/api/investigation-set-overview` (split into `set-objective` + status writes).

## Out of scope (deferred)

- Variant scope beyond parameters (initial-state edits, process swaps).
- Linking interventions to variants/runs (currently text-only).
- Stored-data cleanup of the per-variant nested `intervention` field on disk (the v3 migration drops it in-memory; the field may persist in on-disk v2 specs).

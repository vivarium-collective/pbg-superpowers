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
  ├── Investigations (in investigations/<slug>/investigation.yaml)
  │     └── Studies[]     (list of study slugs; DAG from each study's parent_studies)
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

> "Study" is the canonical per-experiment term. "Investigation" now refers specifically to the higher-level collection container (`investigations/<slug>/investigation.yaml`). The v2 legacy use of "investigation" as a synonym for "study" is retired in the UI; backend aliases (`investigation:` body key, `/api/investigation-*`) remain for backwards compatibility but should not be used in new code.

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

### Investigation

An Investigation is a **named collection of studies** with an explicit cross-study dependency DAG. Used to group studies that together answer a higher-level research question.

- **On disk:** `<workspace>/investigations/<slug>/investigation.yaml`. Note the filename is `investigation.yaml`, NOT `spec.yaml` — the legacy v2 `investigations/<name>/spec.yaml` files are Studies (auto-migrated to v3) and are excluded by the new iset walker.
- **Shape:** `{schema_version, name, title, status, question, hypothesis, description, studies[], expert_docs[], acceptance_criteria[]}`. `studies` is a list of study slugs (members); `acceptance_criteria` is a list of `{study, behavior}` pairs linking criteria to specific `expected_behavior[i].name` entries on member studies.
- **API**:
  - `GET /api/iset-list` — summaries (name, title, status, n_studies).
  - `GET /api/iset/<name>` — full investigation + resolved studies (each carrying normalized `parent_studies` for DAG layout).
  - No write endpoints exist yet; skills write YAML directly (atomic tmp-file + rename).
- **Dashboard render**: Investigations tab cards → DAG canvas on click; rail sidebar groups studies under their investigation header; "Ungrouped" bucket for studies not in any investigation; topological order within each group.
- **Skill**: `/pbg-investigation` for CRUD + scaffold-from-plan.

> Note: the DAG topology is computed from each member study's `parent_studies:` field at render time. The `studies:` list on the investigation controls visibility/grouping only, not execution order.

### Study dependencies (DAG)

Studies can declare ordering via the optional `parent_studies:` field. Each entry is either a bare slug (legacy, normalized to `{study, condition: tests-passed}`) or an object `{study: <slug>, condition: tests-passed | ran | complete}`. Conditions:

- `tests-passed` — parent's `tests.last_results.passed > 0` AND `failed == 0`.
- `ran` — parent's `status` is one of `{ran, complete}`.
- `complete` — parent's `status == complete`.

**API**: `GET /api/investigations` returns each study with computed `parent_studies` (normalized to object form), `blocked: bool`, and `blocked_by: [{study, condition, missing-diagnostic}]`. A parent that doesn't resolve to a known study slug surfaces as `parent-not-found` in `blocked_by`.

**Dashboard rendering**: the Studies tab's `Dependencies` sort (default) topologically orders studies — roots first, alphabetical within depth. Each card shows:

- `Depends on: <links> (<condition>) · ...` (blue, clickable).
- `Blocks: <links> · ...` (grey, clickable).
- `🔒 blocked` status pill with the `blocked_by` diagnostics in tooltip, when `blocked: true`.

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
| `/pbg-investigation` | Investigation | Investigation YAML | **All Investigation CRUD + scaffold-from-plan.** Writes YAML directly (no write endpoints yet). |
| `/pbg-viz` | Visualization | Visualization | Adds a viz to a study. |
| `/pbg-report` | Study | Report file | Renders study summary to markdown. |
| `/pbg-workspace` | Workspace | Workspace state | Workspace-level commands. |

## v4 reserved field names {#v4-reserved-fields}

Schema v4 (the current dashboard validation target) reserves these top-level
field names on `study.yaml`. **If you author v3 specs (the common case) with
fields that share these names but a different shape, the v3→v4 auto-migration
will collide and surface validation errors.**

| Field | Required shape (v4) | Notes |
|---|---|---|
| `tests` | object: `{auto_discover: bool, data_source: enum, pytest_args: list, last_results: object\|null}` | The dashboard runs pytest from `studies/<slug>/tests/` and writes results back here. |
| `references` | list of `{file: str, section?: str}` objects | Resolves to markdown / PDF docs. |
| `implementation_tasks` | string (markdown blob) | Narrative; not parsed. |

**If you have a custom field with one of these names but a different shape,
rename your custom field.** Common renames the team has adopted:

- `references:` (dict) → `bibliography:`
- `implementation_tasks:` (list of strings) → `tasks:`

If your spec is intentionally v4-shape, set `schema_version: 4` at the top
level so the migration short-circuits and you get the v4 validator directly.

When a collision occurs, the validation error message now includes a `Note:`
suffix naming the reserved field, so you know to rename your custom field
rather than guessing at a shape mismatch.

## Migration notes

- **v2 → v3 on read:** `vivarium_dashboard.lib.spec_migration.migrate_v2_to_v3` runs automatically in `load_spec`. Skills never need to invoke it.
- **v2 endpoints still aliased:** `/api/investigation-add-viz`, `/api/investigation-render-viz`, and a few others remain as aliases of their `/api/study-*` v3 counterparts. New skill code should prefer the `study-` form.
- **Removed in v3:** `/api/study-set-baseline-params` (covered by `study-variant-set-params` + the new baseline-list shape); `/api/investigation-set-overview` (split into `set-objective` + status writes).

## Out of scope (deferred)

- Variant scope beyond parameters (initial-state edits, process swaps).
- Linking interventions to variants/runs (currently text-only).
- Stored-data cleanup of the per-variant nested `intervention` field on disk (the v3 migration drops it in-memory; the field may persist in on-disk v2 specs).
